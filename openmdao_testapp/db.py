
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
    
    for n in cur:
        print '\nTable %s' % n[0]
        cur2 = conn.cursor()
        cur2.execute("SELECT * from %s;" % n[0])
        for result in cur2:
            for r in result:
                if isinstance(r, basestring):
                    print r[0:50],', ',
                else:
                    print r,', ',
            print ''
            

if __name__ == '__main__':
    main()

