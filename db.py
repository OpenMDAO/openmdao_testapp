
import sys
import sqlite3
from optparse import OptionParser

import model

def main():
    parser = OptionParser()
    parser.add_option("-d", "--db", action="store", type="string", 
                      dest='db', help="db file")
    
    (options, args) = parser.parse_args(sys.argv[1:])

    if options.db is None:
        parser.print_help()
        print "db file must be specified"
        sys.exit(-1)

    conn = sqlite3.connect(options.db)

    cmd = "SELECT name from sqlite_master WHERE type='table' ORDER BY name;"
    cur = conn.cursor()
    cur.execute(cmd)
    cur2 = conn.cursor()
    
    tables = []
    
    print 'TABLES:'
    for n in cur:
        print n[0]
        tables.append(n[0])
        cmd = "SELECT * from %s;" % n[0]
        cur2.execute(cmd)
        for v in cur2:
            print v
            
    
    for tab in tables:
        cur = conn.cursor()
        cur.execute('SELECT * from %s')
        for result in cur:
            for r in result:
                if isinstance(r, basestring):
                    print r[0:50],
                else:
                    print r,
            print ''



if __name__ == '__main__':
    main()

