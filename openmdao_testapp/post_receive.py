
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
import time
import re
import atexit
from threading import Thread
from Queue import Queue
import ConfigParser

import web

import model

from openmdao.util.git import download_github_tar

APP_DIR = model.APP_DIR

config = ConfigParser.ConfigParser()
config.readfp(open(os.path.join(APP_DIR, 'testing.cfg'), 'r'))

REPO_URL = config.get('openmdao_testing', 'repo_url')
#LOCAL_REPO_DIR = config.get('openmdao_testing', 'local_repo_dir')
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

commit_queue = Queue()

def fixmulti(txt):
    """adds unescaped html line breaks"""
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


def activate_and_run(envdir, cmd):
    """"
    Runs the given command from within an activated virtual environment located
    in the specified directory.
    
    Returns the output and return code of the command as a tuple (output, returncode).
    """
    if sys.platform.startswith('win'):
        command = ['Scripts/activate.bat',  '&&'] + cmd
    else:
        command = ['source ./bin/activate', '&&'] + cmd
    
    # activate the environment and run command
    
    print("running %s in %s" % (' '.join(command), envdir))
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

def get_env_dir(commit_id):
    repo_dir = os.path.join(APP_DIR, commit_id, 'repo')
    for f in os.listdir(repo_dir):
        if os.path.isdir(os.path.join(repo_dir, f)) and \
                f.startswith('OpenMDAO-OpenMDAO-Framework'):
            return os.path.join(repo_dir, f, 'devenv')
   
    raise OSError("Couldn't locate source tree for commit %s" % commit_id)


def push_docs(commit_id):
    if DEVDOCS_DIR:
        cmd = ['openmdao', 'push_docs', '-d', DEVDOCS_DIR, 
               'openmdao@web103.webfaction.com']
        try:
            out, ret = activate_and_run(get_env_dir(commit_id), cmd)
        except Exception as err:
            out = str(err)
            ret = -1
        model.new_doc_info(commit_id, out)
        return out, ret
    else:
        return '', 0 # allow update of production dev docs to be turned off during debugging


def do_tests(q):
    """Loops over commit notifications and runs them sequentially."""
    while True:
        payload = q.get(block=True)
        try:
            retval = test_commit(payload)
        except (Exception, SystemExit) as err:
            print str(err)

def send_mail(commit_id, retval, msg, sender=FROM_EMAIL, 
              dest_emails=RESULTS_EMAILS):
    status = 'succeeded' if retval == 0 else 'failed'
    try:
        web.sendmail(sender, dest_emails,
                     'test %s for commit %s' % (status, commit_id),
                     msg)
    except OSError as err:
        print str(err)
        print "ERROR: failed to send notification email"
        
        
def build_environment(commit_id):
    print 'building local environment'
    envdir = get_env_dir(commit_id)
    tardir = os.path.dirname(envdir)
    startdir = os.getcwd()
    os.chdir(tardir)
    try:
        p = subprocess.Popen([PY, 'go-openmdao-dev.py', '--gui'],
                             cwd=os.getcwd(), shell=True)
        p.wait()
        ret = p.returncode
    except Exception as err:
        print str(err)
        ret = -1
    finally:
        os.chdir(startdir)
    if ret != 0:
        print "ERROR building local environment. return code=%s" % ret
    return ret

def test_commit(payload):
    """Run the test suite on the commit specified in payload."""
    
    startdir = os.getcwd()
    
    repo = payload['repository']['url']
    commit_id = payload['after']
    branch = payload['ref'].split('/')[-1]
    
    if repo != REPO_URL:
        print 'ignoring commit: repo URL %s does not match expected repo URL (%s)' % (repo, REPO_URL)
        return -1
    
    if branch not in REPO_BRANCHES:
        print 'branch is %s' % branch
        print 'ignoring commit %s: branch is not one of %s' % (commit_id,
                                                               REPO_BRANCHES)
        return -1
    
    # make sure this commit hasn't been tested yet
    cmnts = model.get_host_tests(commit_id)
    if cmnts != None and len(list(cmnts)) > 0:
        print "commit %s has already been tested" % commit_id
        return -1
    
    tmp_results_dir = os.path.join(APP_DIR, commit_id, 'host_results')
    tmp_repo_dir = os.path.join(APP_DIR, commit_id, 'repo')
    os.makedirs(tmp_results_dir)
    os.makedirs(tmp_repo_dir)
    
    # grab a copy of the commit
    print "downloading source tarball from github for commit %s" % commit_id
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
        print 'cmd = ',' '.join(cmd)
        out, ret = _run_sub(cmd, env=os.environ.copy(), cwd=os.getcwd())
        print 'test_branch return code = %s' % ret
        
        # untar the repo tarfile
        print 'untarring test repo locally'
        os.chdir(tmp_repo_dir)
        try:
            tar = tarfile.open(tarpath)
            tar.extractall()
            tar.close()
        finally:
            os.chdir(startdir)
        print 'untar successful'
            
        bldret = build_environment(commit_id)
        if ret == 0:
            ret = bldret

        process_results(commit_id, ret, tmp_results_dir, out)
    except (Exception, SystemExit) as err:
        ret = -1
        process_results(commit_id, ret, tmp_results_dir, str(err))
    finally:
        shutil.rmtree(os.path.join(APP_DIR, commit_id))
        
    return ret


def parse_test_output(output):
    """Given a string of test results, try to extract the following:
        number of passing tests,
        number of failing tests,
        total elapsed time
    Returns a tuple of the form (passes, fails, skips, elapsed_time)
    """
    numtests = fails = skips = 0
    elapsed_time = 'unknown'
    
    last = output[-1024:]
    ran = re.search('Ran ([0-9]+) tests in ([0-9\.]+s)', last)
    if ran:
        numtests = int(ran.group(1))
        elapsed_time = ran.group(2)
        fail = re.search('FAILED \((.+)\)', last)
        if fail:
            parts = fail.group(1).split(',')
            for part in parts:
                fails += int(part.split('=')[1])
        skipped = re.search('SKIP=([0-9]+)', last)
        if skipped:
            skips = int(skipped.group(1))
        else:
            skips = 0
    
    return (numtests-fails-skips, fails, skips, elapsed_time)


def process_results(commit_id, returncode, results_dir, output):
    msg = "\n\nFull test results can be found here: %s" % os.path.join(APP_URL,
                                                                       'hosts',
                                                                       commit_id)
    for host in os.listdir(results_dir):
        try:
            with open(os.path.join(results_dir, host, 'run.out'), 'r') as f:
                results = f.read()
            passes, fails, skips, elapsed_time = parse_test_output(results)
            model.new_test(commit_id, results, host,
                           passes=passes, fails=fails, skips=skips,
                           elapsed_time=elapsed_time)
        except Exception as err:
            model.new_test(commit_id, str(err), host)

    try:
        if returncode == 0:
            docout, returncode = push_docs(commit_id)  # update the dev docs if the tests passed
            if returncode == 0:
                docout = '\n\nDev docs built successfully\n'
        else:
            docout = "\n\nDev docs were not built\n"
            model.new_doc_info(commit_id, docout)
    except Exception as err:
        returncode = -1
        docout = str(err)

    send_mail(commit_id, returncode, output+docout+msg)

        
    
if __name__ == "__main__":
    
    tester = Thread(target=do_tests, name='tester', args=(commit_queue,))
    tester.daemon = True
    tester.start()
    
    ### Url mappings

    if 'test' in sys.argv:
        top = '/p_r/'
    else:
        top = '/'

    urls = (
        top, 'Index',
        top+'run', 'Run',
        top+'view/(\w+)/(\w+)', 'View',
        top+'viewdocs/(\w+)', 'ViewDocs',
        top+'hosts/(\w+)', 'Hosts',
        top+'delete/(\w+)', 'Delete',
    )
    

    app = web.application(urls, globals())
    app.run()


