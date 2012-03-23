"""
A script to run an OpenMDAO branch test triggered by a post_recieve
hook on github.

"""

import os
import sys
import shutil
import json
import pprint
import StringIO
import subprocess
import tarfile
import fnmatch
import tempfile
import time
import re
import atexit
from threading import Thread
from Queue import Queue
import ConfigParser
import zlib

import web

import model

from openmdao.util.git import download_github_tar
from openmdao.devtools.utils import settings, put, run, cd

APP_DIR = model.APP_DIR

config = ConfigParser.ConfigParser()
config.readfp(open(os.path.join(APP_DIR, 'testing.cfg'), 'r'))

TOP = config.get('openmdao_testing', 'top')
PORT = config.get('openmdao_testing', 'port')
REPO_URL = config.get('openmdao_testing', 'repo_url')
APP_URL = config.get('openmdao_testing', 'app_url')
REPO_BRANCHES = [s.strip() for s in config.get('openmdao_testing', 
                                               'repo_branches').split('\n')]
FROM_EMAIL = config.get('openmdao_testing', 'from_email')
RESULTS_EMAILS = [s.strip() for s in config.get('openmdao_testing', 
                                                'results_emails').split('\n')]
PY = config.get('openmdao_testing', 'py')
HOSTS = [s.strip() for s in config.get('openmdao_testing', 
                                       'hosts').split('\n')]
TEST_ARGS = [s.strip() for s in config.get('openmdao_testing', 
                                           'test_args').split('\n') if s.strip()]

DEVDOCS_DIR = config.get('openmdao_testing', 'devdocs_location').strip()

# map of commit id to temp directory
directory_map = {}

commit_queue = Queue()

def fixmulti(txt):
    """adds unescaped html line breaks"""
    txt = zlib.decompress(txt)
    txt = web.net.htmlquote(txt)
    return txt.replace('\n', '<br/>')
    
    
### Templates
t_globals = {
    'fixmulti': fixmulti
    }

render = web.template.render(os.path.join(APP_DIR,'templates'), 
                             base='base', globals=t_globals)

class Index:

    def GET(self):
        """ Show commit index """
        return render.index(model.get_commits())

    
class Hosts:

    def GET(self, commit_id):
        """ Show hosts for a given test """
        tests = model.get_host_tests(commit_id)
        return render.hosts(tests, commit_id, 
                            os.path.join(REPO_URL,'commit',commit_id),
                            os.path.join(APP_URL,'viewdocs',commit_id))

class View:

    def GET(self, host, commit_id):
        """ View results for a single commit on a host"""
        test = model.get_test(host, commit_id)
        return render.view(test,
                           os.path.join(REPO_URL,'commit',commit_id))

class ViewDocs:

    def GET(self, commit_id):
        """ View doc build results for a single commit on a host"""
        bld = model.get_docbuild(commit_id)
        if bld is None:
            return "Docs are not available yet"
        else:
            return render.viewdocs(bld)

class Delete:

    def POST(self, commit_id):
        """ Delete all results for a commit """
        model.delete_test(commit_id)
        raise web.seeother('/p_r')

class Run:

    def POST(self):
        """ Run tests for a commit """
        data = web.input('payload')
        payload = json.loads(data.payload)
        commit_queue.put(payload)


########################################################################

def log(msg, level=0):
    print msg
    sys.stdout.flush()
    
def activate_and_run(envdir, cmd):
    """"
    Runs the given command from within an activated virtual environment located
    in the specified directory.
    
    Returns the output and return code of the command as a tuple (output, returncode).
    """
    if sys.platform.startswith('win'):
        command = ['Scripts/activate.bat',  '&&'] + cmd
    else:
        command = ['.', './bin/activate', '&&'] + cmd
    
    # activate the environment and run command
    
    log("running %s in %s" % (' '.join(command), envdir))
    env = os.environ.copy()
    for name in ['VIRTUAL_ENV','_OLD_VIRTUAL_PATH','_OLD_VIRTUAL_PROMPT']:
        if name in env: 
            del env[name]

    return _run_sub(' '.join(command), env=env, shell=True, cwd=envdir)


def _run_sub(cmd, **kwargs):
    """Runs a subprocess and returns its output (stdout and stderr combined)
    and return code.
    """
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, **kwargs)
    output = p.communicate()[0]
    return (output, p.returncode)

def push_docs(commit_id, doc_host):
    if DEVDOCS_DIR and doc_host is not None:
        tarname = 'html.tar.gz'
        tarpath = os.path.join(get_commit_dir(commit_id), 'host_results', 
                               doc_host, tarname)
        try:
            with settings(host_string='openmdao@web103.webfaction.com'):
                # tar up the docs so we can upload them to the server
                # put the docs on the server and untar them
                put(tarpath, '%s/%s' % (DEVDOCS_DIR, tarname))
                with cd(DEVDOCS_DIR):
                    run('tar xzf %s' % tarname)
                    run('rm -rf dev_docs')
                    run('mv html dev_docs')
                    run('rm -f %s' % tarname)
        except Exception as err:
            log('ERROR: push_docs failed: %s' % str(err))
            out = str(err)
            ret = -1
        else:
            log('push_docs was successful')
            out = 'Docs built successfully'
            ret = 0
            
        model.new_doc_info(commit_id, zlib.compress(out, 9))
        return out, ret
    else:
        log('push_docs was skipped')
        return '', 0 # allow update of production dev docs to be turned off during debugging


def do_tests(q):
    """Loops over commit notifications and runs them sequentially."""
    while True:
        payload = q.get(block=True)
        try:
            retval = test_commit(payload)
        except (Exception, SystemExit) as err:
            log(str(err))

def send_mail(commit_id, retval, msg, sender=FROM_EMAIL, 
              dest_emails=RESULTS_EMAILS):
    status = 'succeeded' if retval == 0 else 'failed'
    try:
        web.sendmail(sender, dest_emails,
                     'test %s for commit %s' % (status, commit_id),
                     msg)
    except OSError as err:
        log(str(err))
        log("ERROR: failed to send notification email")

def get_commit_dir(commit_id):
    if commit_id not in directory_map:
        directory_map[commit_id] = tempfile.mkdtemp()
    return directory_map[commit_id]

def test_commit(payload):
    """Run the test suite on the commit specified in payload."""
    
    startdir = os.getcwd()
    
    repo = payload['repository']['url']
    commit_id = payload['after']
    branch = payload['ref'].split('/')[-1]
    
    if repo != REPO_URL:
        log('ignoring commit: repo URL %s does not match expected repo URL (%s)' % (repo, REPO_URL))
        return -1
    
    if branch not in REPO_BRANCHES:
        log('branch is %s' % branch)
        log('ignoring commit %s: branch is not one of %s' % (commit_id,
                                                             REPO_BRANCHES))
        return -1
    
    # make sure this commit hasn't been tested yet
    cmnts = model.get_host_tests(commit_id)
    if cmnts != None and len(list(cmnts)) > 0:
        log("commit %s has already been tested" % commit_id)
        return -1
    
    commit_dir = get_commit_dir(commit_id)
    tmp_results_dir = os.path.join(commit_dir, 'host_results')
    tmp_repo_dir = os.path.join(commit_dir, 'repo')
    os.makedirs(tmp_results_dir)
    os.makedirs(tmp_repo_dir)
    
    # grab a copy of the commit
    log("downloading source tarball from github for commit %s" % commit_id)
    prts = repo.split('/')
    repo_name = prts[-1]
    org_name = prts[-2]
    tarpath = download_github_tar(org_name, repo_name, commit_id, dest=tmp_repo_dir)

    cmd = ['openmdao', 'test_branch', 
           '-o', tmp_results_dir,
           '-f', tarpath,
           ]
    for host in HOSTS:
        cmd.append('--host=%s' % host)
        
    if TEST_ARGS:
        cmd.append('--testargs="%s"' % ' '.join(TEST_ARGS))
    
    try:
        log('cmd = %s' % ' '.join(cmd))
        out, ret = _run_sub(cmd, env=os.environ.copy(), cwd=os.getcwd())
        log('test_branch return code = %s' % ret)

        process_results(commit_id, ret, tmp_results_dir, out)
    except (Exception, SystemExit) as err:
        log('ERROR during local build: %s' % str(err))
        ret = -1
        process_results(commit_id, ret, tmp_results_dir, str(err))
    finally:
        d = get_commit_dir(commit_id)
        del directory_map[commit_id]
        log('removing temp commit directory %s' % d)
        shutil.rmtree(d)
        
    return ret


def parse_test_output(output):
    """Given a test results filename, try to extract the following:
        number of passing tests,
        number of failing tests,
        total elapsed time
    Returns a tuple of the form (passes, fails, skips, elapsed_time)
    """
    numtests = fails = skips = 0
    elapsed_time = 'unknown'
    
    for last in output.rsplit('\n'):
        if numtests == 0:
            ran = re.search('Ran ([0-9]+) tests in ([0-9\.]+s)', last)
            if ran:
                numtests = int(ran.group(1))
                elapsed_time = ran.group(2)
        if fails == 0:
            fail = re.search('FAILED \((.+)\)', last)
            if fail:
                parts = fail.group(1).split(',')
                for part in parts:
                    if not part.startswith('SKIP'):
                        fails += int(part.split('=')[1])
        if skips == 0:
            skipped = re.search('SKIP=([0-9]+)', last)
            if skipped:
                skips = int(skipped.group(1))
    
    return (numtests-fails-skips, fails, skips, elapsed_time)


def process_results(commit_id, returncode, results_dir, output):
    msg = "\n\nFull test results can be found here: %s" % os.path.join(APP_URL,
                                                                       'hosts',
                                                                       commit_id)
    doc_host = None
    for host in os.listdir(results_dir):
        try:
            with open(os.path.join(results_dir, host, 'run.out'), 'r') as f:
                results = f.read()
            passes, fails, skips, elapsed_time = parse_test_output(results)
            model.new_test(commit_id, zlib.compress(results, 9), host,
                           passes=passes, fails=fails, skips=skips,
                           elapsed_time=elapsed_time)
            if returncode == 0 and os.path.isfile(os.path.join(results_dir, host, 'html.tar.gz')):
                doc_host = host
        except Exception as err:
            model.new_test(commit_id, str(err), host)

    try:
        if returncode == 0:
            docout, returncode = push_docs(commit_id, doc_host)  # update the dev docs if the tests passed
            if doc_host is None:
                docout = '\n\nReturn code was 0 but dev docs were not built???\n'
            else:
                docout = '\n\nDev docs built successfully on host %s\n' % doc_host
        else:
            docout = "\n\nDev docs were not built\n"
            model.new_doc_info(commit_id, docout)
    except Exception as err:
        returncode = -1
        docout = str(err)

    send_mail(commit_id, returncode, output+docout+msg)

        
    
def start_server():    
    sys.stderr = sys.stdout
    
    tester = Thread(target=do_tests, name='tester', args=(commit_queue,))
    tester.daemon = True
    tester.start()
    
    ### Url mappings

    urls = (
        TOP, 'Index',
        TOP+'run', 'Run',
        TOP+'view/(\w+)/(\w+)', 'View',
        TOP+'viewdocs/(\w+)', 'ViewDocs',
        TOP+'hosts/(\w+)', 'Hosts',
        TOP+'delete/(\w+)', 'Delete',
    )
    
    sys.argv.append(PORT)

    web.config.debug = False
    
    app = web.application(urls, globals())
    app.run()


if __name__ == "__main__":
    start_server()


