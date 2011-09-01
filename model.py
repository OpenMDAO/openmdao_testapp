import os
import web, datetime
from web.utils import Storage

APP_DIR = os.path.abspath(os.path.dirname(__file__))

db = web.database(dbn='sqlite', 
                  db=os.path.join(APP_DIR,'testdb'))

            
def get_commits():
    ret = []
    commits = db.query('SELECT DISTINCT commit_id from tests')
    for commit in commits:
        tests = db.select('tests', where='commit_id=$commit.commit_id',
                          vars=locals())
        passes = 0
        fails = 0
        for i,test in enumerate(tests):
            if i==0:
                date = test.date
            if test.passes != 0 and test.fails == 0:
                passes += 1
            else:
                fails += 1
        obj = Storage(passes=passes, fails=fails, 
                      commit_id=commit.commit_id, date=date)
        ret.append(obj)
    return ret


def get_host_tests(commit_id):
    try:
        return db.select('tests', where='commit_id=$commit_id', 
                         vars=locals())
    except IndexError:
        return None


def get_test(host, commit_id):
    try:
        return db.query('SELECT * from tests WHERE commit_id=$commit_id and host=$host', 
                         vars=locals())[0]
    except IndexError:
        return None

def new_test(commit_id, results, host, 
             passes=0, fails=0, elapsed_time='unknown'):
    db.insert('tests', commit_id=commit_id, results=results, 
              date=datetime.datetime.utcnow(),
              host=host, passes=passes, fails=fails,
              elapsed_time=elapsed_time)

def delete_test(commit_id):
    db.delete('tests', where="commit_id=$commit_id", vars=locals())


