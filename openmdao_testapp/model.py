"""
Functions that interact with the testing database.
"""

import os
import sqlite3
import zlib
import web, datetime
from web.utils import Storage

APP_DIR = os.path.abspath(os.path.dirname(__file__))

db = web.database(dbn='sqlite', 
                  db=os.path.join(APP_DIR,'testdb'))

            
def get_commits():
    commits = []
    commitdict = {}
    tests = db.select('tests', order='date DESC')
    for test in tests:
        if test.commit_id in commitdict:
            obj = commitdict[test.commit_id]
        else:
            obj = Storage(passes=0, fails=0, skips=0,
                          commit_id=test.commit_id, date=test.date)
            commits.append(obj)
            commitdict[test.commit_id] = obj
            
        if test.fails > 0 or test.passes == 0:
            obj.fails += 1
        else:
            obj.passes += 1
            
    return commits


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
             passes=0, fails=0, skips=0, elapsed_time='unknown'):
    db.insert('tests', commit_id=commit_id, results=sqlite3.Binary(results), 
              date=datetime.datetime.utcnow(),
              host=host, passes=passes, fails=fails, skips=skips,
              elapsed_time=elapsed_time)
    
def get_docbuild(commit_id):
    try:
        return db.query('SELECT * from docbuilds WHERE commit_id=$commit_id', 
                         vars=locals())[0]
    except IndexError:
        return None


def new_doc_info(commit_id, results):
    db.insert('docbuilds', commit_id=commit_id, results=sqlite3.Binary(zlib.compress(results,9)))

    
def delete_test(commit_id):
    db.delete('tests', where="commit_id=$commit_id", vars=locals())
    db.delete('docbuilds', where="commit_id=$commit_id", vars=locals())


def dump():
    print 'Tests:'
    tests = db.select('tests', order='date DESC')
    for test in tests:
        print "%s  %s  p:%s  f:%s  s:%s t:%s plat:%s date:%s" % (test.commit_id,
                                                                 test.host,
                                                                 test.passes,
                                                                 test.fails,
                                                                 test.skips,
                                                                 test.elapsed_time,
                                                                 test.platform,
                                                                 test.date)

    print 'Docbuilds:'
    tests = db.select('docbuilds')
    for test in tests:
        print "%s  %s" % (test.commit_id, test.results[0:50])
        


