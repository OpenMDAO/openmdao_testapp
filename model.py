import os
import web, datetime

APP_DIR = '/home/openmdao/webapps/custom_app'

db = web.database(dbn='sqlite', 
                  db=os.path.join(APP_DIR,'testdb'))

def get_tests():
    return db.select('tests')

def get_test(commit_id):
    try:
        return db.select('tests', where='commit_id=$commit_id', 
                         vars=locals())[0]
    except IndexError:
        return None

def new_test(commit_id, results):
    print 'adding new test: %s' % commit_id
    db.insert('tests', commit_id=commit_id, results=results, 
              date=datetime.datetime.utcnow())

def delete_test(commit_id):
    db.delete('tests', where="commit_id=$commit_id", vars=locals())


