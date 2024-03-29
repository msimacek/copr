import json
import os.path
import shutil
import time

from bunch import Bunch

from .createrepo import createrepo, createrepo_unsafe


class Action(object):
    """ Object to send data back to fronted

    :param multiprocessing.Queue events: collects events for logging
    :param multiprocessing.Lock lock: Global lock for backend
    :param backend.callback.FrontendCallback frontent_callback:
        object to post data back to frontend

    :param str destdir: filepath with build results

    :param dict action: action job, fields:
        - action_type: main field determining what action to apply
        # TODO: describe actions

    """

    def __init__(self, events, action, lock,
                 frontend_callback, destdir,
                 front_url, results_root_url):
        super(Action, self).__init__()
        self.frontend_callback = frontend_callback
        self.destdir = destdir
        self.data = action
        self.events = events
        self.lock = lock
        self.front_url = front_url
        self.results_root_url = results_root_url

    def add_event(self, what):
        self.events.put({"when": time.time(), "who": "action", "what": what})

    def handle_legal_flag(self):
        self.add_event("Action legal-flag: ignoring")

    def handle_createrepo(self, result):
        self.add_event("Action create repo")
        data = json.loads(self.data["data"])
        username = data["username"]
        projectname = data["projectname"]
        chroots = data["chroots"]

        failure = False
        for chroot in chroots:
            self.add_event("Creating repo for: {}/{}/{}".format(username, projectname, chroot))

            path = os.path.join(self.destdir, username, projectname, chroot)

            errcode, _, err = createrepo_unsafe(path=path, lock=self.lock)
            if errcode != 0 or err.strip():
                self.add_event("Error making local repo: {0}".format(err))
                failure = True

        if failure:
            result.result = ActionResult.FAILURE
        else:
            result.result = ActionResult.SUCCESS

    def handle_rename(self, result):
        self.add_event("Action rename")
        old_path = os.path.normpath(os.path.join(
            self.destdir, self.data["old_value"]))
        new_path = os.path.normpath(os.path.join(
            self.destdir, self.data["new_value"]))

        if os.path.exists(old_path):
            if not os.path.exists(new_path):
                shutil.move(old_path, new_path)
                result.result = ActionResult.SUCCESS
            else:
                result.message = "Destination directory already exist."
                result.result = ActionResult.FAILURE
        else:  # nothing to do, that is success too
            result.result = ActionResult.SUCCESS
        result.job_ended_on = time.time()

    def handle_delete_copr_project(self):
        self.add_event("Action delete copr")
        project = self.data["old_value"]
        path = os.path.normpath(self.destdir + '/' + project)
        if os.path.exists(path):
            self.add_event("Removing copr {0}".format(path))
            shutil.rmtree(path)

    def handle_delete_build(self):
        self.add_event("Action delete build")
        project = self.data["old_value"]

        ext_data = json.loads(self.data["data"])
        username = ext_data["username"]
        projectname = ext_data["projectname"]

        packages = [os.path.basename(x).replace(".src.rpm", "")
                    for x in ext_data["pkgs"].split()]

        path = os.path.join(self.destdir, project)

        self.add_event("Packages to delete {0}".format(' '.join(packages)))
        self.add_event("Copr path {0}".format(path))

        try:
            chroot_list = os.listdir(path)
        except OSError:
            # already deleted
            chroot_list = []

        for chroot in chroot_list:
            self.add_event("In chroot {0}".format(chroot))
            altered = False

            # We need to delete the files only if they belong
            # to the build. For example if my build fails and I send
            # fixed pkg with the same version again, it succeeds and
            # than I delete the failed, it would delete the succeeded
            # files as well - that would be wrong.
            for pkg in packages:
                if self.data["object_type"] == "build-succeeded" or (
                        self.data["object_type"] == "build-failed" and
                        os.path.exists(os.path.join(path, chroot, pkg, "fail"))):

                    pkg_path = os.path.join(path, chroot, pkg)
                    if os.path.isdir(pkg_path):
                        self.add_event("Removing build {0}".format(pkg_path))
                        shutil.rmtree(pkg_path)
                        altered = True
                    else:
                        self.add_event(
                            "Package {0} dir not found in chroot {1}"
                            .format(pkg, chroot))

            if altered:
                self.add_event("Running createrepo")

                result_base_url = "/".join(
                    [self.results_root_url, username, projectname, chroot])
                _, _, err = createrepo(
                    path=os.path.join(path, chroot), lock=self.lock,
                    front_url=self.front_url, base_url=result_base_url,
                    username=username, projectname=projectname
                )
                if err.strip():
                    self.add_event(
                        "Error making local repo: {0}".format(err))

            log_path = os.path.join(
                path, chroot,
                'build-{0}.log'.format(self.data['object_id']))

            if os.path.isfile(log_path):
                self.add_event("Removing log {0}".format(log_path))
                os.unlink(log_path)

    def run(self):
        """ Handle action (other then builds) - like rename or delete of project """
        result = Bunch()
        result.id = self.data["id"]

        action_type = self.data["action_type"]

        if action_type == ActionType.DELETE:
            if self.data["object_type"] == "copr":
                self.handle_delete_copr_project()
            elif self.data["object_type"] in \
                    ["build-succeeded", "build-skipped", "build-failed"]:
                self.handle_delete_build()

            result.result = ActionResult.SUCCESS

        elif action_type == ActionType.LEGAL_FLAG:
            self.handle_legal_flag()

        elif action_type == ActionType.RENAME:
            self.handle_rename(result)

        elif action_type == ActionType.CREATEREPO:
            self.handle_createrepo(result)

        if "result" in result:
            if result.result == ActionResult.SUCCESS and \
                    not getattr(result, "job_ended_on", None):
                result.job_ended_on = time.time()

            self.frontend_callback.update({"actions": [result]})


class ActionType(object):
    DELETE = 0
    RENAME = 1
    LEGAL_FLAG = 2
    CREATEREPO = 3


class ActionResult(object):
    WAITING = 0
    SUCCESS = 1
    FAILURE = 2
