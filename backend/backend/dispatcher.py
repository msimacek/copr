import re
import os
import sys
import time
import fcntl
import Queue
import json
import subprocess
import multiprocessing

import ansible
import ansible.utils
from ansible import callbacks
from bunch import Bunch
from setproctitle import setproctitle
from IPy import IP

import errors
import mockremote
from callback import FrontendCallback

try:
    import fedmsg
except ImportError:
    pass  # fedmsg is optional


class SilentPlaybookCallbacks(callbacks.PlaybookCallbacks):

    """ playbook callbacks - quietly! """

    def __init__(self, verbose=False):
        super(SilentPlaybookCallbacks, self).__init__()
        self.verbose = verbose

    def on_start(self):
        callbacks.call_callback_module("playbook_on_start")

    def on_notify(self, host, handler):
        callbacks.call_callback_module("playbook_on_notify", host, handler)

    def on_no_hosts_matched(self):
        callbacks.call_callback_module("playbook_on_no_hosts_matched")

    def on_no_hosts_remaining(self):
        callbacks.call_callback_module("playbook_on_no_hosts_remaining")

    def on_task_start(self, name, is_conditional):
        callbacks.call_callback_module(
            "playbook_on_task_start", name, is_conditional)

    def on_vars_prompt(self, varname,
                       private=True, prompt=None, encrypt=None,
                       confirm=False, salt_size=None, salt=None):

        result = None
        sys.stderr.write(
            "***** VARS_PROMPT WILL NOT BE RUN IN THIS KIND OF PLAYBOOK *****\n")

        callbacks.call_callback_module(
            "playbook_on_vars_prompt", varname, private=private,
            prompt=prompt, encrypt=encrypt, confirm=confirm,
            salt_size=salt_size, salt=None)

        return result

    def on_setup(self):
        callbacks.call_callback_module("playbook_on_setup")

    def on_import_for_host(self, host, imported_file):
        callbacks.call_callback_module(
            "playbook_on_import_for_host", host, imported_file)

    def on_not_import_for_host(self, host, missing_file):
        callbacks.call_callback_module(
            "playbook_on_not_import_for_host", host, missing_file)

    def on_play_start(self, pattern):
        callbacks.call_callback_module("playbook_on_play_start", pattern)

    def on_stats(self, stats):
        callbacks.call_callback_module("playbook_on_stats", stats)


class WorkerCallback(object):

    def __init__(self, logfile=None):
        self.logfile = logfile

    def log(self, msg):
        if self.logfile:
            now = time.strftime("%F %T")
            try:
                with open(self.logfile, 'a') as lf:
                    fcntl.flock(lf, fcntl.LOCK_EX)
                    lf.write(str(now) + ': ' + msg + '\n')
                    fcntl.flock(lf, fcntl.LOCK_UN)
            except (IOError, OSError), e:
                sys.stderr.write("Could not write to logfile {0} - {1}\n"
                                 .format(self.logfile, str(e)))


class Worker(multiprocessing.Process):

    def __init__(self, opts, jobs, events, worker_num,
                 ip=None, create=True, callback=None, lock=None):

        # base class initialization
        multiprocessing.Process.__init__(self, name="worker-builder")

        # job management stuff
        self.jobs = jobs
        # event queue for communicating back to dispatcher
        self.events = events
        self.worker_num = worker_num
        self.ip = ip
        self.opts = opts
        self.kill_received = False
        self.callback = callback
        self.create = create
        self.lock = lock
        self.frontend_callback = FrontendCallback(opts)
        if not self.callback:
            self.logfile = os.path.join(
                self.opts.worker_logdir,
                "worker-{0}.log".format(self.worker_num))
            self.callback = WorkerCallback(logfile=self.logfile)

        if ip:
            self.callback.log("creating worker: {0}".format(ip))
            self.event("worker.create", "creating worker: {ip}", dict(ip=ip))
        else:
            self.callback.log("creating worker: dynamic ip")
            self.event("worker.create", "creating worker: dynamic ip")

    def event(self, topic, template, content=None):
        """ Multi-purpose logging method.

        Logs messages to two different destinations:
            - To log file
            - The internal "events" queue for communicating back to the
              dispatcher.
            - The fedmsg bus.  Messages are posted asynchronously to a
              zmq.PUB socket.

        """

        content = content or {}
        what = template.format(**content)

        if self.ip:
            who = "worker-{0}-{1}".format(self.worker_num, self.ip)
        else:
            who = "worker-{0}".format(self.worker_num)

        self.callback.log("event: who: {0}, what: {1}".format(who, what))
        self.events.put({"when": time.time(), "who": who, "what": what})
        try:
            content["who"] = who
            content["what"] = what
            if self.opts.fedmsg_enabled:
                fedmsg.publish(modname="copr", topic=topic, msg=content)
        # pylint: disable=W0703
        except Exception, e:
            # XXX - Maybe log traceback as well with traceback.format_exc()
            self.callback.log("failed to publish message: {0}".format(e))

    def spawn_instance(self, retry=0):
        """call the spawn playbook to startup/provision a building instance"""

        self.callback.log("spawning instance begin")
        start = time.time()

        # Does not work, do not know why. See:
        # https://groups.google.com/forum/#!topic/ansible-project/DNBD2oHv5k8
        #stats = callbacks.AggregateStats()
        #playbook_cb = SilentPlaybookCallbacks(verbose=False)
        #runner_cb = callbacks.DefaultRunnerCallbacks()
        # fixme - extra_vars to include ip as a var if we need to specify ips
        # also to include info for instance type to handle the memory requirements of builds
        # play = ansible.playbook.PlayBook(stats=stats, playbook=self.opts.spawn_playbook,
        #                     callbacks=playbook_cb, runner_callbacks=runner_cb,
        #                     remote_user="root", transport="ssh")
        # play.run()
        try:
            result = subprocess.check_output(
                "ansible-playbook -c ssh {0}".format(self.opts.spawn_playbook),
                shell=True)

        except subprocess.CalledProcessError as e:
            result = e.output
            sys.stderr.write("{0}\n".format(result))
            self.callback.log("CalledProcessError: {0}".format(result))
            # well mostly we run out of space in OpenStack, wait some time and
            # try again
            if retry < 3:
                time.sleep(self.opts.sleeptime)
                self.spawn_instance(retry + 1)
            else:
                # FIXME: this can't work and whole retry is implemented
                # incorrectly, should use decorator instead
                raise subprocess.CalledProcessError, None, sys.exc_info()[2]
        self.callback.log("Raw output from playbook: {0}".format(result))
        match = re.search(r'IP=([^\{\}"]+)', result, re.MULTILINE)

        if not match:
            return None

        ipaddr = match.group(1)

        self.callback.log("spawning instance end")
        self.callback.log("got instance ip: {0}".format(ipaddr))
        self.callback.log(
            "Instance spawn/provision took {0} sec".format(time.time() - start))

        if self.ip:
            return self.ip

        # for i in play.SETUP_CACHE:
        #    if i =="localhost":
        #        continue
        #    return i
        try:
            IP(ipaddr)
            return ipaddr
        except ValueError:
            # if we get here we"re in trouble
            self.callback.log(
                "No IP back from spawn_instance - dumping cache output")
            self.callback.log(str(result))
            self.callback.log("Test spawn_instance playbook manually")
            return None

    def terminate_instance(self, ip):
        """call the terminate playbook to destroy the building instance"""
        self.callback.log("terminate instance begin")

        #stats = callbacks.AggregateStats()
        #playbook_cb = SilentPlaybookCallbacks(verbose=False)
        #runner_cb = callbacks.DefaultRunnerCallbacks()
        # play = ansible.playbook.PlayBook(host_list=ip +",", stats=stats, playbook=self.opts.terminate_playbook,
        #                     callbacks=playbook_cb, runner_callbacks=runner_cb,
        #                     remote_user="root", transport="ssh")
        # play.run()
        subprocess.check_output(
            "/usr/bin/ansible-playbook -c ssh -i '{0},' {1} ".format(
                ip, self.opts.terminate_playbook),
            shell=True)

        self.callback.log("terminate instance end")

    def parse_job(self, jobfile):
        # read the json of the job in
        # break out what we need return a bunch of the info we need
        try:
            build = json.load(open(jobfile))
        except ValueError:
            # empty file?
            return None
        jobdata = Bunch()
        jobdata.pkgs = build["pkgs"].split(" ")
        jobdata.repos = [r for r in build["repos"].split(" ") if r.strip()]
        jobdata.chroot = build["chroot"]
        jobdata.buildroot_pkgs = build["buildroot_pkgs"]
        jobdata.memory_reqs = build["memory_reqs"]
        if build["timeout"]:
            jobdata.timeout = build["timeout"]
        else:
            jobdata.timeout = self.opts.timeout
        jobdata.destdir = os.path.normpath(
            os.path.join(self.opts.destdir,
                         build["copr"]["owner"]["name"],
                         build["copr"]["name"]))

        jobdata.build_id = build["id"]
        jobdata.results = os.path.join(
            self.opts.results_baseurl,
            build["copr"]["owner"]["name"],
            build["copr"]["name"] + "/")

        jobdata.copr_id = build["copr"]["id"]
        jobdata.user_id = build["user_id"]
        jobdata.user_name = build["copr"]["owner"]["name"]
        jobdata.copr_name = build["copr"]["name"]
        return jobdata

    # maybe we move this to the callback?
    def post_to_frontend(self, data):
        """send data to frontend"""
        i = 10
        while i > 0:
            result = self.frontend_callback.post_to_frontend(data)
            if not result:
                self.callback.log(self.frontend_callback.msg)
                i -= 1
                time.sleep(5)
            else:
                i = 0
        return result

    # maybe we move this to the callback?
    def mark_started(self, job):

        build = {"id": job.build_id,
                 "started_on": job.started_on,
                 "results": job.results,
                 "chroot": job.chroot,
                 "status": 3,  # running
                 }
        data = {"builds": [build]}

        if not self.post_to_frontend(data):
            raise errors.CoprWorkerError(
                "Could not communicate to front end to submit status info")

    # maybe we move this to the callback?
    def return_results(self, job):

        self.callback.log(
            "{0} status {1}. Took {2} seconds".format(
                job.build_id, job.status, job.ended_on - job.started_on))

        build = {
            "id": job.build_id,
            "ended_on": job.ended_on,
            "status": job.status,
            "chroot": job.chroot,
        }

        data = {"builds": [build]}

        if not self.post_to_frontend(data):
            raise errors.CoprWorkerError(
                "Could not communicate to front end to submit results")

        os.unlink(job.jobfile)

    def run(self):
        """
        Worker should startup and check if it can function
        for each job it takes from the jobs queue
        run opts.setup_playbook to create the instance
        do the build (mockremote)
        terminate the instance.
        """

        setproctitle("worker {0}".format(self.worker_num))
        while not self.kill_received:
            try:
                jobfile = self.jobs.get()
            except Queue.Empty:
                break

            # parse the job json into our info
            job = self.parse_job(jobfile)

            if job is None:
                self.callback.log(
                    'jobfile {0} is mangled, please investigate'.format(
                        jobfile))

                time.sleep(self.opts.sleeptime)
                continue

            # FIXME
            # this is our best place to sanity check the job before starting
            # up any longer process

            job.jobfile = jobfile

            # spin up our build instance
            if self.create:
                try:
                    ip = self.spawn_instance()
                    if not ip:
                        raise errors.CoprWorkerError(
                            "No IP found from creating instance")

                except ansible.errors.AnsibleError, e:
                    self.callback.log(
                        "failure to setup instance: {0}".format(e))

                    raise

            try:
                # This assumes there are certs and a fedmsg config on disk
                try:
                    if self.opts.fedmsg_enabled:
                        fedmsg.init(
                            name="relay_inbound",
                            cert_prefix="copr",
                            active=True)

                except Exception, e:
                    self.callback.log(
                        "failed to initialize fedmsg: {0}".format(e))

                status = 1  # succeeded
                job.started_on = time.time()
                self.mark_started(job)

                template = "build start: user:{user} copr:{copr}" \
                    " build:{build} ip:{ip}  pid:{pid}"

                content = dict(user=job.user_name, copr=job.copr_name,
                               build=job.build_id, ip=ip, pid=self.pid)
                self.event("build.start", template, content)

                template = "chroot start: chroot:{chroot} user:{user}" \
                    "copr:{copr} build:{build} ip:{ip}  pid:{pid}"

                content = dict(chroot=job.chroot, user=job.user_name,
                               copr=job.copr_name, build=job.build_id,
                               ip=ip, pid=self.pid)

                self.event("chroot.start", template, content)

                chroot_destdir = os.path.normpath(
                    job.destdir + '/' + job.chroot)

                # setup our target dir locally
                if not os.path.exists(chroot_destdir):
                    try:
                        os.makedirs(chroot_destdir)
                    except (OSError, IOError), e:
                        msg = "Could not make results dir" \
                              " for job: {0} - {1}".format(chroot_destdir,
                                                           str(e))

                        self.callback.log(msg)
                        status = 0  # fail

                if status == 1:  # succeeded
                    # FIXME
                    # need a plugin hook or some mechanism to check random
                    # info about the pkgs
                    # this should use ansible to download the pkg on the remote system
                    # and run a series of checks on the package before we
                    # start the build - most importantly license checks.

                    self.callback.log("Starting build: id={0} builder={1}"
                                      " timeout={2} destdir={3}"
                                      " chroot={4} repos={5}".format(
                                          job.build_id, ip,
                                          job.timeout, job.destdir,
                                          job.chroot, str(job.repos)))

                    self.callback.log("building pkgs: {0}".format(
                        ' '.join(job.pkgs)))

                    try:
                        chroot_repos = list(job.repos)
                        chroot_repos.append(job.results + '/' + job.chroot)
                        chrootlogfile = "{0}/build-{1}.log".format(
                            chroot_destdir, job.build_id)

                        macros = {
                            "copr_username": job.user_name,
                            "copr_projectname": job.copr_name,
                            "vendor": "Fedora Project COPR ({0}/{1})".format(
                                job.user_name, job.copr_name)
                        }

                        mr = mockremote.MockRemote(
                            builder=ip,
                            timeout=job.timeout,
                            destdir=job.destdir,
                            chroot=job.chroot,
                            cont=True,
                            recurse=True,
                            repos=chroot_repos,
                            macros=macros,
                            lock=self.lock,
                            buildroot_pkgs=job.buildroot_pkgs,
                            callback=mockremote.CliLogCallBack(
                                quiet=True, logfn=chrootlogfile))

                        mr.build_pkgs(job.pkgs)

                    except mockremote.MockRemoteError, e:
                        # record and break
                        self.callback.log("{0} - {1}".format(ip, e))
                        status = 0  # failure
                    else:
                        # we can"t really trace back if we just fail normally
                        # check if any pkgs didn"t build
                        if mr.failed:
                            status = 0  # failure

                    self.callback.log(
                        "Finished build: id={0} builder={1}"
                        " timeout={2} destdir={3}"
                        " chroot={4} repos={5}".format(
                            job.build_id, ip,
                            job.timeout, job.destdir,
                            job.chroot, str(job.repos)))

                job.ended_on = time.time()

                job.status = status
                self.return_results(job)
                self.callback.log("worker finished build: {0}".format(ip))
                template = "build end: user:{user} copr:{copr} build:{build}" \
                    " ip:{ip}  pid:{pid} status:{status}"

                content = dict(user=job.user_name, copr=job.copr_name,
                               build=job.build_id, ip=ip, pid=self.pid,
                               status=job.status)
                self.event("build.end", template, content)

            finally:
                # clean up the instance
                if self.create:
                    self.terminate_instance(ip)