
import sys
import sqlite3
from optparse import OptionParser

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
    for n in cur:
        print n
        cmd = "SELECT * from %s;" % n
        cur2.execute(cmd)
        for v in cur2:
            print v



if __name__ == '__main__':
    main()

