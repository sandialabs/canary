# Copyright NTESS. See COPYRIGHT file for details.
#
# SPDX-License-Identifier: MIT

import configparser
import functools
import io
import json
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from contextlib import contextmanager
from urllib.parse import urlencode
from urllib.request import HTTPHandler
from urllib.request import Request
from urllib.request import build_opener
from urllib.request import urlopen


def api_access_required(fun):
    @functools.wraps(fun)
    def inner(self, *args, **kwargs):
        if self.access_token is None:
            raise ValueError(f"{self.name}'s access_token must be set")

        if self.gitlab_id is None:
            raise ValueError(f"{self.name}'s project or group id must be set")

        if self.api_url is None:
            raise ValueError(f"{self.name}'s api url must be set")

        return fun(self, *args, **kwargs)

    return inner


class repo:
    def __init__(self, *, url, path=None, api_url=None, access_token=None, project_id=None):
        if path is None and url is None:
            raise ValueError("path or url must be defined")
        self.url = self.sanitize_url(url)
        self.path = path
        self.name = os.path.basename(self.path or self.sanitize_url(url))
        self.access_token = access_token or os.getenv("ACCESS_TOKEN")
        self.project_id = project_id or os.getenv("CI_PROJECT_ID")
        self.api_url = api_url or os.getenv("CI_API_V4_URL")
        self._issues = {}
        self._commits = None
        self._merge_requests = {}

    def __repr__(self):
        return f"gitlab_repo({self.url})"

    def __str__(self):
        return f"gitlab_repo({self.url})"

    @property
    def gitlab_id(self):
        return self.project_id

    def build_api_url(self, *, path, query=None):
        url = f"{self.api_url}/{path}"
        if query is not None:
            url = f"{url}?{query}"
        return url

    def clone_url(self, protocol):
        if protocol == "https":
            return f"https://{self.url}"
        elif protocol == "git":
            url, group, *rest = self.url.split(os.path.sep)
            path = os.path.sep.join(rest)
            return f"git@{url}:{group}/{path}"
        else:
            raise ValueError(f"Unrecognized protocol {protocol}")

    def remove_source_tree(self):
        if self.cloned:
            shutil.rmtree(self.path)

    def cloned(self):
        return self.path is not None

    @staticmethod
    def _clone(*, url, branch=None, recurse=False, shallow=False, quiet=False):
        cmd = ["clone"]
        if recurse:
            cmd.append("--recurse-submodules")
        if branch:
            cmd.extend(["--single-branch", f"--branch={branch}"])
        if shallow:
            cmd.extend(["--depth", "1"])
            if recurse:
                cmd.append("--shallow-submodules")
        if quiet:
            cmd.append("--quiet")
        cmd.append(url)
        rc = git(*cmd)
        if rc != 0:
            raise ValueError(f"Failed to clone {url}")
        path = os.path.join(os.getcwd(), os.path.basename(url))
        if path.endswith(".git"):
            path = path[:-4]
        return path

    def clone(self, protocol="https", branch=None, recurse=False, shallow=False, quiet=False):
        url = self.clone_url(protocol)
        self.path = repo._clone(
            url=url, branch=branch, recurse=recurse, shallow=shallow, quiet=quiet
        )

    @classmethod
    def from_clone(cls, *, url, branch=None, recurse=False, shallow=False):
        path = repo._clone(url=url, branch=branch, recurse=recurse, shallow=shallow)
        return cls(path=path, url=url)

    @classmethod
    def from_checkout(cls, *, path):
        git_dir = os.path.join(path, ".git")
        if not os.path.exists(git_dir):
            raise ValueError(f"{path} does not appear to be a git clone")
        file = os.path.join(git_dir, "config")
        if not os.path.exists(file):
            raise ValueError(f"{git_dir} does not contain a config file")
        config = configparser.ConfigParser()
        config.read(file)
        section, option = 'remote "origin"', "url"
        try:
            url = config.get(section, option)
        except configparser.NoSectionError:
            msg = f"git config {file!r} does not have a {section!r} field"
            raise ValueError(msg) from None
        except configparser.NoOptionError:
            msg = f"{section!r} does not define {option!r}"
            raise ValueError(msg) from None
        return cls(path=os.path.abspath(path), url=url)

    @staticmethod
    def sanitize_url(url):
        if url.startswith("git@"):
            url = url[4:].replace(":", "/")
        elif url.startswith("https://"):
            url = url[8:]
        if url.endswith(".git"):
            url = url[:-4]
        return url

    @contextmanager
    def branch(self, name, create=False):
        cb = self._current_branch
        if cb != name:
            self._checkout(name, create=create)
        yield self
        if cb != name:
            self._checkout(cb)

    def branches(self):
        with working_dir(self.path):
            out = git("branch", "-a", stdout=str)
            branches = []
            for line in split(out, sep="\n"):
                line = line.split()[0]
                if line.startswith("remotes/origin/HEAD"):
                    continue
                elif line.startswith("remotes/origin/"):
                    branches.append(line.replace("remotes/origin/", ""))
                else:
                    branches.append(line)
        return branches

    def branch_exists(self, name):
        return name in self.branches()

    def _checkout(self, name, create=False):
        args = ["-b"] if create else []
        args.append(name)
        with working_dir(self.path):
            git("checkout", *args)

    def pull(self, *args):
        cmd = ["pull"] + list(args)
        with working_dir(self.path):
            git(*cmd)

    def fetch(self, *args):
        cmd = ["fetch"] + list(args)
        with working_dir(self.path):
            git(*cmd)

    def checkout(self, *args, commit=None):
        cmd = ["checkout"]
        if commit is not None:
            cmd.append(commit)
        cmd.extend(args)
        with working_dir(self.path):
            git(*cmd)

    def clean(self, *args):
        with working_dir(self.path):
            git("clean", *args)

    def reset(self, *args):
        cmd = ["reset"]
        cmd.extend(args)
        with working_dir(self.path):
            git(*cmd)

    def update_submodules(self):
        with working_dir(self.path):
            git("submodule", "update")

    def add(self, item, force=False):
        args = ["add"]
        if force:
            args.append("-f")
        args.append(item)
        with working_dir(self.path):
            git(*args)

    def remove(self, item, force=False):
        args = ["rm"]
        if force:
            args.append("-f")
        if os.path.isdir(item):
            args.append("-r")
        args.append(item)
        with working_dir(self.path):
            git(*args)

    def commit(self, message, add=False):
        logging.info(f"Committing changes to {self.name}")
        with working_dir(self.path):
            args = ["-a"] if add else []
            args.extend(["-m", message])
            git("commit", *args)

    def push(self, tags=False):
        logging.info(f"Pushing changes to {self.name}")
        with working_dir(self.path):
            args = []
            if tags:
                args.append("--tags")
                if tags == "force":
                    args.append("-f")
            args.extend(["-u", "origin"])
            current_branch = self._current_branch
            if current_branch != "HEAD":
                args.append(current_branch)
            git("push", *args)

    def tag(self, name):
        logging.info(f"Tagging {self.name} at {self.sha()} with {name}")
        with working_dir(self.path):
            tags = split(git("tag", stdout=str), sep="\n")
            if name in tags:
                git("tag", "-d", name)
            git("tag", name)
        return self.sha()

    def sha(self):
        with working_dir(self.path):
            return git("rev-parse", "HEAD", stdout=str).strip()

    @property
    def _current_branch(self):
        with working_dir(self.path):
            return git("rev-parse", "--abbrev-ref", "HEAD", stdout=str).strip()

    @api_access_required
    def upload(self, *, file):
        try:
            import requests
        except ImportError:
            logging.warning("uploading files requires the requests library")
            return None

        url = self.build_api_url(path=f"projects/{self.project_id}/uploads")
        headers = {"PRIVATE-TOKEN": self.access_token}
        files = {"file": open(file, "rb")}
        response = requests.post(url, headers=headers, files=files)
        return response.json()

    @api_access_required
    def release(self, *, name, tag, assets=None):
        headers = {"PRIVATE-TOKEN": self.access_token}
        params = {
            "name": name,
            "tag_name": tag,
            "description": f"{self.name} release {name}",
        }
        encoded_params = urlencode(params)
        url = self.build_api_url(path=f"projects/{self.project_id}/releases", query=encoded_params)
        request = Request(url=url, headers=headers, method="POST")
        request.get_method = lambda: "POST"
        opener = build_opener(HTTPHandler)
        with opener.open(request):
            pass

        if assets is not None:
            for filename in assets:
                self.link(tag=tag, filename=filename, fileurl=assets[filename])

        get_url = f"{url}/{tag}"
        request = Request(url=get_url, headers=headers)
        return json.load(urlopen(request))

    @api_access_required
    def link(self, *, tag, filename, fileurl):
        url = self.build_api_url(path=f"projects/{self.project_id}/releases/{tag}/assets/links")
        headers = {"PRIVATE-TOKEN": self.access_token}
        data = urlencode({"name": filename, "url": fileurl}).encode("utf-8")
        request = Request(url=url, headers=headers, data=data, method="POST")
        request.get_method = lambda: "POST"
        opener = build_opener(HTTPHandler)
        with opener.open(request):
            pass

    @api_access_required
    def issues(self, state=None):
        """Get issues for this project"""
        if state not in self._issues:
            issues = []
            header = {"PRIVATE-TOKEN": self.access_token}
            page = 1
            while True:
                base_url = self.build_api_url(path=f"projects/{self.project_id}/issues")
                params = {"page": str(page), "per_page": "100"}
                if state is not None:
                    params["state"] = state
                params = urlencode(params)
                url = f"{base_url}?{params}"
                logging.debug(url)
                request = Request(url=url, headers=header)
                payload = json.load(urlopen(request))
                if not payload:
                    break
                issues.extend(payload)
                page += 1
            self._issues[state] = issues
        return self._issues[state]

    @api_access_required
    def commits(self):
        """Get issues for this project"""
        if self._commits is None:
            self._commits = []
            header = {"PRIVATE-TOKEN": self.access_token}
            page = 1
            while True:
                base_url = self.build_api_url(path=f"projects/{self.project_id}/repository/commits")
                params = {"page": str(page), "per_page": "100"}
                params = urlencode(params)
                url = f"{base_url}?{params}"
                logging.debug(url)
                request = Request(url=url, headers=header)
                payload = json.load(urlopen(request))
                if not payload:
                    break
                self._commits.extend(payload)
                page += 1
        return self._commits

    @api_access_required
    def merge_requests(self, state=None):
        """Get merge_requests for this project"""
        if state not in self._merge_requests:
            merge_requests = []
            header = {"PRIVATE-TOKEN": self.access_token}
            page = 1
            pid = self.project_id
            base_url = self.build_api_url(path=f"projects/{pid}/merge_requests")
            while True:
                params = {"page": str(page), "per_page": "50"}
                if state is not None:
                    params["state"] = state
                params = urlencode(params)
                url = f"{base_url}?{params}"
                logging.debug(url)
                request = Request(url=url, headers=header)
                payload = json.load(urlopen(request))
                if not payload:
                    break
                merge_requests.extend(payload)
                page += 1
            self._merge_requests[state] = merge_requests
        return self._merge_requests[state]

    @api_access_required
    def issue(self, issue_no):
        url = self.build_api_url(path=f"projects/{self.project_id}/issues/{issue_no}")
        headers = {"PRIVATE-TOKEN": self.access_token}
        request = Request(url=url, headers=headers)
        return json.load(urlopen(request))

    @api_access_required
    def move_issue(self, issue_no, *, to_project_id):
        # TODO: I (tjfulle) haven't figured out how to use urllib to do what
        # the --form argument to curl does
        header = ["--header", f"PRIVATE-TOKEN: {self.access_token}"]
        form = ["--form", f"to_project_id={to_project_id}"]
        url = self.build_api_url(path=f"projects/{self.project_id}/issues/{issue_no}/move")
        args = header + form + [url]
        curl(*args)

    @api_access_required
    def edit_issue(self, issue_no, *, data=None, notes=None):
        if data is None and notes is None:
            raise ValueError("data or notes must be defined")
        if data is not None and notes is not None:
            raise ValueError("only one of data or notes can be defined")
        if isinstance(notes, str):
            notes = {"body": notes}
        headers = {"PRIVATE-TOKEN": self.access_token}
        base_url = self.build_api_url(path=f"projects/{self.project_id}/issues/{issue_no}")
        encoded_params = urlencode(data or notes)

        if data is not None:
            url = f"{base_url}?{encoded_params}"
            method = "PUT"
        else:
            url = f"{base_url}/notes?{encoded_params}"
            method = "POST"

        request = Request(url=url, headers=headers, method=method)
        request.get_method = lambda: method
        opener = build_opener(HTTPHandler)
        with opener.open(request):
            pass

    @api_access_required
    def new_issue(self, *, data):
        headers = {"PRIVATE-TOKEN": self.access_token}
        base_url = self.build_api_url(path=f"projects/{self.project_id}/issues")
        encoded_params = urlencode(data)
        url = f"{base_url}?{encoded_params}"
        request = Request(url=url, headers=headers, method="POST")
        request.get_method = lambda: "POST"
        issue = json.load(urlopen(request))
        return issue.get("iid")

    @api_access_required
    def tags(self):
        url = self.build_api_url(path=f"projects/{self.project_id}/repository/tags")
        headers = {"PRIVATE-TOKEN": self.access_token}
        request = Request(url=url, headers=headers)
        return json.load(urlopen(request))

    def tag_exists(self, name):
        return name in self.tags()


class group(repo):
    def __init__(self, *, url, group_id, access_token=None, api_url=None):
        self.url = self.sanitize_url(url)
        self.name = os.path.basename(self.sanitize_url(url))
        self.access_token = access_token or os.getenv("ACCESS_TOKEN")
        self.group_id = group_id
        self.api_url = api_url or os.getenv("CI_API_V4_URL")
        self._issues = {}

    @property
    def gitlab_id(self):
        return self.group_id

    def build_api_url(self, *, path, query=None):
        url = f"{self.api_url}/{path}"
        if query is not None:
            url = f"{url}?{query}"
        return url

    def clone_url(self, protocol):
        raise NotImplementedError


class merge_request:
    def __init__(self, api_v4_url, project_id, iid, access_token):
        self.iid = iid
        self.project_id = project_id
        self.access_token = access_token
        self.api_v4_url = api_v4_url
        self._mr_data = None
        self._project_data = None
        self._target_data = None
        self._source_data = None

    def build_api_url(self, *, path, query=None):
        url = f"{self.api_v4_url}/{path}"
        if query is not None:
            url = f"{url}?{query}"
        return url

    @property
    def author(self):
        author = self.get_property("author")
        if author is None:
            return "unknown"
        return author["username"]

    @property
    def author_email(self):
        author = self.get_property("author")
        if author is None:
            return os.getenv("GITLAB_USER_EMAIL")
        return f"{author['username']}@sandia.gov"

    @property
    def description(self):
        return self.get_property("description")

    @property
    def labels(self):
        return self.get_property("labels", [])

    @property
    def id(self):
        return self.get_property("id")

    @property
    def title(self):
        return self.get_property("title")

    @property
    def url(self):
        return self.get_property("web_url")

    @property
    def source_url(self):
        return self.get_source_property("web_url")

    @property
    def target_url(self):
        return self.get_target_property("web_url")

    @property
    def source_branch(self):
        return self.get_property("source_branch")

    @property
    def target_branch(self):
        return self.get_property("target_branch")

    @property
    def source_branch_url(self):
        branch_name = self.get_property("target_branch")
        source_url = self.source_url
        if branch_name is None or source_url is None:
            return
        return f"{source_url}/-/tree/{branch_name}"

    @property
    def target_branch_url(self):
        branch_name = self.get_property("target_branch")
        target_url = self.target_url
        if branch_name is None or target_url is None:
            return
        return f"{target_url}/-/tree/{branch_name}"

    @property
    def source_project_id(self):
        return self.get_property("source_project_id")

    @property
    def target_project_id(self):
        return self.get_property("target_project_id")

    @property
    def project_url(self):
        return self.get_project_property("web_url")

    @property
    def source_project_url(self):
        return self.get_source_property("web_url")

    @property
    def target_project_url(self):
        return self.get_target_property("web_url")

    @property
    def project_path(self):
        return self.get_project_property("path")

    @property
    def source_project_path(self):
        return self.get_source_property("path")

    @property
    def target_project_path(self):
        return self.get_target_property("path")

    @property
    def ci_job_url(self):
        # Only set if run by a pipeline
        return os.getenv("CI_JOB_URL")

    @property
    def ci_job_name(self):
        # Only set if run by a pipeline
        return os.getenv("CI_JOB_NAME")

    @property
    def data(self):
        if self._mr_data is None:
            if self.access_token is None:
                return None
            pid = self.project_id
            url = self.build_api_url(path=f"projects/{pid}/merge_requests/{self.iid}")
            logging.info(f"Fetching merge request data for MR {self.iid}")
            headers = {"PRIVATE-TOKEN": self.access_token}
            request = Request(url=url, headers=headers)
            self._mr_data = json.load(urlopen(request))
        return self._mr_data

    def fetch_project_data(self, pid):
        url = self.build_api_url(path=f"projects/{pid}")
        logging.info(f"Fetching project data for project {pid}")
        headers = {"PRIVATE-TOKEN": self.access_token}
        request = Request(url=url, headers=headers)
        return json.load(urlopen(request))

    @property
    def project_data(self):
        if self._project_data is None:
            if self.access_token is None:
                return None
            self._project_data = self.fetch_project_data(self.project_id)
        return self._project_data

    @property
    def source_data(self):
        if self._source_data is None:
            if self.access_token is None:
                return None
            pid = self.source_project_id
            if pid == self.project_id:
                self._source_data = self.project_data
            else:
                self._source_data = self.fetch_project_data(pid)
        return self._source_data

    @property
    def target_data(self):
        if self._target_data is None:
            if self.access_token is None:
                return None
            pid = self.target_project_id
            if pid == self.project_id:
                self._source_data = self.project_data
            else:
                self._target_data = self.fetch_project_data(pid)
        return self._target_data

    def get_property(self, name, default=None):
        data = self.data
        return default if data is None else data.get(name, default)

    def get_project_property(self, name, default=None):
        data = self.project_data
        return default if data is None else data.get(name, default)

    def get_target_property(self, name, default=None):
        data = self.target_data
        return default if data is None else data.get(name, default)

    def get_source_property(self, name, default=None):
        data = self.source_data
        return default if data is None else data.get(name, default)

    def add_note(self, note):
        opener = build_opener(HTTPHandler)
        headers = {"PRIVATE-TOKEN": self.access_token}
        params = {"body": note}
        encoded_params = urlencode(params)
        pid = self.project_id
        url = self.build_api_url(
            path=f"projects/{pid}/merge_requests/{self.iid}/notes", query=encoded_params
        )
        request = Request(url=url, headers=headers, method="POST")
        request.get_method = lambda: "POST"
        with opener.open(request):
            pass

    def remove_labels(self, *labels):
        opener = build_opener(HTTPHandler)
        headers = {"PRIVATE-TOKEN": self.access_token}
        params = {"remove_labels": ",".join(labels)}
        encoded_params = urlencode(params)
        pid = self.project_id
        url = self.build_api_url(
            path=f"projects/{pid}/merge_requests/{self.iid}", query=encoded_params
        )
        request = Request(url=url, headers=headers, method="PUT")
        request.get_method = lambda: "PUT"
        with opener.open(request):
            pass

    def add_labels(self, *labels):
        opener = build_opener(HTTPHandler)
        headers = {"PRIVATE-TOKEN": self.access_token}
        params = {"add_labels": ",".join(labels)}
        encoded_params = urlencode(params)
        pid = self.project_id
        url = self.build_api_url(
            path=f"projects/{pid}/merge_requests/{self.iid}", query=encoded_params
        )
        request = Request(url=url, headers=headers, method="PUT")
        request.get_method = lambda: "PUT"
        with opener.open(request):
            pass


def download_file(download_url, filename=None):
    filename = filename or os.path.basename(download_url)
    with urlopen(download_url) as response:
        with open(filename, "wb") as fh:
            shutil.copyfileobj(response, fh)


def get_job_artifacts(api_v4_url, project_id, jobid, access_token=None, dest=None):
    url = f"{api_v4_url}/projects/{project_id}/jobs/{jobid}/artifacts"
    dest = os.path.abspath(dest or os.getcwd())
    with tmpdir():
        headers = {}
        if access_token is not None:
            headers["PRIVATE-TOKEN"] = access_token
        logging.info(f"Downloading artifacts from {url}")
        request = Request(url=url, headers=headers)
        response = urlopen(request)
        f = zipfile.ZipFile(io.BytesIO(response.read()))
        f.extractall(".")
        files = os.listdir(".")
        for file in files:
            if os.path.isdir(file):
                shutil.copytree(file, f"{dest}/{file}")
            else:
                shutil.copy(file, dest)
    return files


@contextmanager
def tmpdir():
    temporary_dir = tempfile.mkdtemp()
    save_cwd = os.getcwd()
    try:
        os.chdir(temporary_dir)
        yield
    finally:
        os.chdir(save_cwd)
        force_remove(temporary_dir)


@contextmanager
def working_dir(dirname):
    save_cwd = os.getcwd()
    try:
        os.chdir(dirname)
        yield
    finally:
        os.chdir(save_cwd)


def force_remove(path):
    if os.path.isfile(path):
        os.remove(path)
    elif os.path.isdir(path):
        shutil.rmtree(path)


def git(subcommand, *args, **kwargs):
    cmd = ["git", subcommand] + list(args)
    if kwargs.get("stdout") is str:
        kwargs.pop("stdout")
        return check_output(cmd, **kwargs)
    return call(cmd, **kwargs)


def call(args, **kwargs):
    p = subprocess.Popen(args, **kwargs)
    p.wait()
    return p.returncode


def check_output(args, **kwargs):
    try:
        output = subprocess.check_output(args, **kwargs)
        return output.decode("utf-8").strip()
    except subprocess.CalledProcessError as e:
        logging.warn(str(e))
        return None


def curl(*args, **kwargs):
    cmd = ["curl"] + list(args)
    return call(cmd, **kwargs)


def split(arg, sep=None):
    if not arg:
        return []
    return [_.strip() for _ in arg.split(sep) if _.split()]
