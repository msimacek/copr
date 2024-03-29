#!/usr/bin/python -ttu

from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import

import ConfigParser
import grp
import lockfile
import logging
import multiprocessing
import optparse
import os
import pwd
import signal
import sys
import time
from collections import defaultdict

import daemon
import requests
import setproctitle
from bunch import Bunch
from retask.task import Task
from retask.queue import Queue
from retask import ConnectionError

from backend.exceptions import CoprBackendError
from backend.dispatcher import Worker
from backend.actions import Action
from backend.callback import FrontendCallback
from backend.helpers import BackendConfigReader


def _get_conf(cp, section, option, default, mode=None):
    """
    To make returning items from config parser less irritating

    :param mode: convert obtained value, possible modes:
      - None (default): do nothing
      - "bool" or "boolean"
      - "int"
      - "float"
    """

    if cp.has_section(section) and cp.has_option(section, option):
        if mode is None:
            return cp.get(section, option)
        elif mode in ["bool", "boolean"]:
            return cp.getboolean(section, option)
        elif mode == "int":
            return cp.getint(section, option)
        elif mode == "float":
            return cp.getfloat(section, option)
    return default


class CoprJobGrab(multiprocessing.Process):

    """
    Fetch jobs from the Frontend
    - submit them to the jobs queue for workers
    """

    def __init__(self, opts, events, lock):
        # base class initialization
        multiprocessing.Process.__init__(self, name="jobgrab")

        self.opts = opts
        self.events = events
        self.task_queues = []
        for group in self.opts.build_groups:
            self.task_queues.append(Queue("copr-be-{0}".format(group["id"])))
            self.task_queues[group["id"]].connect()
        self.added_jobs = []
        self.lock = lock

    def event(self, what):
        self.events.put({"when": time.time(), "who": "jobgrab", "what": what})

    def load_tasks(self):
        try:
            r = requests.get(
                "{0}/waiting/".format(self.opts.frontend_url),
                auth=("user", self.opts.frontend_auth))
            r_json = r.json()

        except requests.RequestException as e:
            self.event("Error retrieving jobs from {0}: {1}".format(
                       self.opts.frontend_url, e))
            return

        except ValueError as e:
            self.event("Error getting JSON build list from FE {0}"
                       .format(e))
            return

        if "builds" in r_json and r_json["builds"]:
            self.event("{0} jobs returned".format(len(r_json["builds"])))
            count = 0
            for task in r_json["builds"]:
                if "task_id" in task and task["task_id"] not in self.added_jobs:
                    # this will ignore and throw away unconfigured architectures
                    # FIXME: don't do ^
                    arch = task["chroot"].split("-")[2]
                    for group in self.opts.build_groups:
                        if arch in group["archs"]:
                            self.added_jobs.append(task["task_id"])
                            task_obj = Task(task)
                            self.task_queues[group["id"]].enqueue(task_obj)
                            count += 1
                            break
            if count:
                self.event("New jobs: %s" % count)

        if "actions" in r_json and r_json["actions"]:
            self.event("{0} actions returned".format(
                len(r_json["actions"])))

            for action in r_json["actions"]:
                ao = Action(self.events, action, self.lock, destdir=self.opts.destdir,
                            frontend_callback=FrontendCallback(self.opts, self.events),
                            front_url=self.opts.frontend_base_url,
                            results_root_url=self.opts.results_baseurl)
                ao.run()

    def run(self):
        setproctitle.setproctitle("CoprJobGrab")
        abort = False
        try:
            while not abort:
                self.load_tasks()
                time.sleep(self.opts.sleeptime)
        except KeyboardInterrupt:
            return


class CoprLog(multiprocessing.Process):

    """log mechanism where items from the events queue get recorded"""

    def __init__(self, opts, events):

        # base class initialization
        multiprocessing.Process.__init__(self, name="logger")

        self.opts = opts
        self.events = events

        logdir = os.path.dirname(self.opts.logfile)
        if not os.path.exists(logdir):
            os.makedirs(logdir, mode=0o750)

    def setup_log_handler(self):
        sys.stderr.write("Running setup handler {} \n".format(self.opts))
        # setup a log file to write to
        logging.basicConfig(filename=self.opts.logfile, level=logging.DEBUG)

        self.log({"when": time.time(), "who": self.__class__.__name__, "what": "Logger iniated"})

    def log(self, event):

        when = time.strftime("%F %T", time.gmtime(event["when"]))
        msg = "{0} : {1}: {2}".format(when,
                                      event["who"],
                                      event["what"].strip())
        try:
            if self.opts.verbose:
                sys.stderr.write("{0}\n".format(msg))
                sys.stderr.flush()
            logging.debug(msg)

        except (IOError, OSError) as e:

            sys.stderr.write("Could not write to logfile {0} - {1}\n".format(
                self.logfile, e))

    # event format is a dict {when:time, who:[worker|logger|job|main],
    # what:str}
    def run(self):
        setproctitle.setproctitle("CoprLog")
        self.setup_log_handler()
        abort = False
        try:
            while not abort:
                e = self.events.get()
                if "when" in e and "who" in e and "what" in e:
                    self.log(e)
        except KeyboardInterrupt:
            return


class CoprBackend(object):

    """
    Core process - starts/stops/initializes workers
    """

    def __init__(self, config_file=None, ext_opts=None):
        # read in config file
        # put all the config items into a single self.opts bunch

        if not config_file:
            raise CoprBackendError("Must specify config_file")

        self.config_file = config_file
        self.ext_opts = ext_opts  # to stow our cli options for read_conf()
        self.workers_by_group_id = defaultdict(list)
        self.max_worker_num_by_group_id = defaultdict(int)

        self.config_reader = BackendConfigReader(self.config_file, self.ext_opts)
        self.opts = None
        self.update_conf()

        self.lock = multiprocessing.Lock()

        self.task_queues = []
        try:
            for group in self.opts.build_groups:
                group_id = group["id"]
                self.task_queues.append(Queue("copr-be-{0}".format(group_id)))
                self.task_queues[group_id].connect()
        except ConnectionError:
            raise CoprBackendError(
                "Could not connect to a task queue. Is Redis running?")

        # make sure there is nothing in our task queues
        self.clean_task_queues()

        self.events = multiprocessing.Queue()
        # event format is a dict {when:time, who:[worker|logger|job|main],
        # what:str}

        # create logger
        self._logger = CoprLog(self.opts, self.events)
        self._logger.start()

        self.event("Starting up Job Grabber")
        # create job grabber
        self._jobgrab = CoprJobGrab(self.opts, self.events, self.lock)
        self._jobgrab.start()
        self.abort = False

        if not os.path.exists(self.opts.worker_logdir):
            os.makedirs(self.opts.worker_logdir, mode=0o750)

    def event(self, what):
        self.events.put({"when": time.time(), "who": "main", "what": what})

    def update_conf(self):
        self.opts = self.config_reader.read()

    def clean_task_queues(self):
        try:
            for queue in self.task_queues:
                while queue.length:
                    queue.dequeue()
        except ConnectionError:
            raise CoprBackendError(
                "Could not connect to a task queue. Is Redis running?")

    def run(self):
        self.abort = False
        while not self.abort:
            # re-read config into opts
            self.update_conf()

            for group in self.opts.build_groups:
                group_id = group["id"]
                self.event(
                    "# jobs in {0} queue: {1}"
                    .format(group["name"], self.task_queues[group_id].length)
                )
                # this handles starting/growing the number of workers
                if len(self.workers_by_group_id[group_id]) < group["max_workers"]:
                    self.event("Spinning up more workers")
                    for _ in range(group["max_workers"] - len(self.workers_by_group_id[group_id])):
                        self.max_worker_num_by_group_id[group_id] += 1
                        w = Worker(
                            self.opts, self.events,
                            self.max_worker_num_by_group_id[group_id],
                            group_id, lock=self.lock
                        )

                        self.workers_by_group_id[group_id].append(w)
                        w.start()
                self.event("Finished starting worker processes")
                # FIXME - prune out workers
                # if len(self.workers) > self.opts.num_workers:
                #    killnum = len(self.workers) - self.opts.num_workers
                #    for w in self.workers[:killnum]:
                # insert a poison pill? Kill after something? I dunno.
                # FIXME - if a worker bombs out - we need to check them
                # and startup a new one if it happens
                # check for dead workers and abort
                preserved_workers = []
                for w in self.workers_by_group_id[group_id]:
                    if not w.is_alive():
                        self.event("Worker {0} died unexpectedly".format(w.worker_num))
                        if self.opts.exit_on_worker:
                            raise CoprBackendError(
                                "Worker died unexpectedly, exiting")
                        else:
                            w.terminate()  # kill it with a fire
                    else:
                        preserved_workers.append(w)
                self.workers_by_group_id[group_id] = preserved_workers

            time.sleep(self.opts.sleeptime)

    def terminate(self):
        """
        Cleanup backend processes (just workers for now)
        And also clean all task queues as they would survive copr restart
        """

        self.abort = True
        for group in self.opts.build_groups:
            group_id = group["id"]
            for w in self.workers_by_group_id[group_id]:
                self.workers_by_group_id[group_id].remove(w)
                w.terminate()
        self.clean_task_queues()


def parse_args(args):
    parser = optparse.OptionParser("\ncopr-be [options]")
    parser.add_option("-c", "--config", default="/etc/copr/copr-be.conf",
                      dest="config_file",
                      help="config file to use for copr-be run")
    parser.add_option("-d", "--daemonize", default=False, dest="daemonize",
                      action="store_true", help="daemonize or not")
    parser.add_option("-p", "--pidfile",
                      default="/var/run/copr-backend/copr-be.pid",
                      dest="pidfile",
                      help="pid file to use for copr-be if daemonized")
    parser.add_option("-x", "--exit", default=False, dest="exit_on_worker",
                      action="store_true", help="exit on worker failure")
    parser.add_option("-v", "--verbose", default=False, dest="verbose",
                      action="store_true", help="be more verbose")

    opts, args = parser.parse_args(args)
    if not os.path.exists(opts.config_file):
        sys.stderr.write("No config file found at: {0}\n".format(
            opts.config_file))
        sys.exit(1)
    opts.config_file = os.path.abspath(opts.config_file)

    ret_opts = Bunch()
    for o in ("daemonize", "exit_on_worker", "pidfile", "config_file"):
        setattr(ret_opts, o, getattr(opts, o))

    return ret_opts


def main(args):
    opts = parse_args(args)

    try:
        context = daemon.DaemonContext(
            pidfile=lockfile.FileLock(opts.pidfile),
            gid=grp.getgrnam("copr").gr_gid,
            uid=pwd.getpwnam("copr").pw_uid,
            detach_process=opts.daemonize,
            umask=0o22,
            stderr=sys.stderr,
            signal_map={
                signal.SIGTERM: "terminate",
                signal.SIGHUP: "terminate",
            },
        )
        with context:
            cbe = CoprBackend(opts.config_file, ext_opts=opts)
            cbe.run()
    except (Exception, KeyboardInterrupt):
        sys.stderr.write("Killing/Dying\n")
        if "cbe" in locals():
            cbe.terminate()
        raise

if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except KeyboardInterrupt:
        sys.stderr.write("\nUser cancelled, may need cleanup\n")
        sys.exit(0)
