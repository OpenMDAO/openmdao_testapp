
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
import time
from threading import Thread
from Queue import Queue
import ConfigParser

import web

import model

APP_DIR = os.path.abspath(os.path.dirname(__file__))
RESULTS_DIR = os.path.join(APP_DIR, 'host_results')

commit_queue = Queue()


### Url mappings

urls = (
    '/', 'Index',
    '/run', 'Run',
    '/view/(\w+)', 'View',
    '/delete/(\w+)', 'Delete',
)

### Templates
t_globals = {
    'datestr': web.datestr
    }

render = web.template.render(os.path.join(APP_DIR,'templates'), 
                             base='base', globals=t_globals)


def _has_checkouts(repodir):
    cmd = 'git status -s'
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                         env=os.environ, shell=True, cwd=repodir)
    out = p.communicate()[0]
    ret = p.returncode
    if ret != 0:
        raise RuntimeError(
             'error while getting status of git repository from directory %s (return code=%d): %s'
              % (os.getcwd(), ret, out))
    for line in out.split('\n'):
        line = line.strip()
        if len(line)>1 and not line.startswith('?'):
            return True
    return False

def activate_and_run(envdir, cmd):
    """"
    Runs the given command from within an activated OpenMDAO virtual environment located
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
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, **kwargs)
    output = p.communicate()[0]
    return (output, p.returncode)


def do_tests(q):
    while True:
        payload = q.get(block=True)
        try:
            print 'testing payload %s' % payload
            test_commit(payload)
        except Exception as err:
            print str(err)
        

def send_mail(commit_id, retval, msg):
    status = 'succeeded' if retval == 0 else 'failed'
    web.sendmail(FROM_EMAIL, RESULTS_EMAILS,
                 'test %s for commit %s' % (status, commit_id),
                 msg)

def set_branch(branch, commit_id, repodir):
    """Set the local repo to the specified branch as long as the local
    repo is clean, and then pull the latest changes from the remote
    branch.
    """
    if _has_checkouts(repodir):
        send_mail(commit_id, -1, 'branch %s is not clean in repo %s!' % (branch,
                                                                         repodir))
        return
    
    cmd = 'git checkout %s' % branch
    out, ret = _run_sub(cmd, shell=True, cwd=repodir)
    print out
    if ret != 0:
        send_mail(commit_id, ret, "command '%s' failed:\n%s" % (cmd, out))
        return
    
    cmd = 'git pull %s %s' % (REMOTE_NAME, branch)
    out, ret = _run_sub(cmd, shell=True, cwd=repodir)
    print out
    if ret != 0:
        send_mail(commit_id, ret, "command '%s' failed:\n%s" % (cmd, out))
        return


def test_commit(payload):
        #pprint.pprint(payload)
        #print '\n\n--------------------------\n\n'
        
        repo = payload['repository']['url']
        commit_id = payload['after']
        branch = payload['ref'].split('/')[-1]
        
        if repo != REPO_URL:
            print 'ignoring commit: repo URL %s does not match expected repo URL (%s)' % (repo, REPO_URL)
            return
        
        if branch not in REPO_BRANCHES:
            print 'branch is %s' % branch
            print 'ignoring commit %s: branch is not one of %s' % (commit_id,
                                                                   REPO_BRANCHES)
            return
        
        set_branch(branch, commit_id, LOCAL_REPO_DIR)
    
        tmp_results_dir = os.path.join(RESULTS_DIR, commit_id)
        
        cmd = ['test_branch', 
               '-o', tmp_results_dir,
               ]
        for host in HOSTS:
            cmd.append('--host=%s' % host)
            
        cmd += TEST_ARGS
        
        os.makedirs(tmp_results_dir)
        try:
            out, ret = activate_and_run(os.path.join(LOCAL_REPO_DIR,'devenv'), cmd)
            process_results(commit_id, ret, tmp_results_dir, out)
        except Exception as err:
            process_results(commit_id, -1, tmp_results_dir, str(err))
        finally:
            shutil.rmtree(tmp_results_dir)

def process_results(commit_id, returncode, results_dir, output):
    msg = "\n\nFull test results can be found here: %s" % os.path.join(APP_URL,
                                                                       'view',
                                                                       commit_id)
    results = collect_results(results_dir)
    model.new_test(commit_id, results)
    send_mail(commit_id, returncode, output+msg)

def collect_results(results_dir):
    print 'collecting results from %s' % results_dir
    results = StringIO.StringIO()
    for d in os.listdir(results_dir):
        with open(os.path.join(results_dir, d, 'run.out'), 'r') as f:
            for line in f:
                results.write(line)
                results.write('\n')
            results.write('\n---------------------------------\n')
    return results.getvalue()


class Index:

    def GET(self):
        """ Show test index """
        print 'Index:GET'
        tests = model.get_tests()
        return render.index(tests)

class View:

    def GET(self, commit_id):
        print 'View:GET'
        """ View results for a single commit """
        test = model.get_test(commit_id)
        return render.view(test)

class Delete:

    def POST(self, commit_id):
        print 'Delete:POST'
        """ Delete results for a commit """
        model.delete_test(commit_id)
        raise web.seeother('/p_r')

class Run:

    def POST(self):
        print 'Run:POST'
        data = web.input('payload')
        payload = json.loads(data.payload)
        #commit_queue.put(payload)
        test_commit(payload)
        

if __name__ == "__main__":
    config = ConfigParser.ConfigParser()
    config.readfp(open(os.path.join(APP_DIR, 'testing.cfg'), 'r'))
    
    REPO_URL = config.get('openmdao_testing', 'repo_url')
    LOCAL_REPO_DIR = config.get('openmdao_testing', 'local_repo_dir')
    APP_URL = config.get('openmdao_testing', 'app_url')
    REPO_BRANCHES = [s.strip() for s in config.get('openmdao_testing', 
                                                   'repo_branches').split('\n')]
    REMOTE_NAME = config.get('openmdao_testing', 'remote_name')
    FROM_EMAIL = config.get('openmdao_testing', 'from_email')
    RESULTS_EMAILS = [s.strip() for s in config.get('openmdao_testing', 
                                                    'results_emails').split('\n')]
    PY = config.get('openmdao_testing', 'py')
    HOSTS = [s.strip() for s in config.get('openmdao_testing', 
                                           'hosts').split('\n')]
    TEST_ARGS = [s.strip() for s in config.get('openmdao_testing', 
                                               'test_args').split('\n')]
    
    #tester = Thread(target=do_tests, name='tester', args=(commit_queue,))
    #tester.daemon = True
    #print 'starting tester thread'
    #tester.start()
    
    app = web.application(urls, globals())
    print 'running app'
    app.run()


