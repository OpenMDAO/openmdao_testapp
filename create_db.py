
import sys
import sqlite3
from optparse import OptionParser

def main():
    parser = OptionParser()
    parser.add_option("-s", "--schema", action="store", type="string", 
                      dest='schema', help="schema file")
    parser.add_option("-d", "--db", action="store", type="string", 
                      dest='db', help="db file to be created")
    
    (options, args) = parser.parse_args(sys.argv[1:])

    if options.db is None:
        parser.print_help()
        print "db file must be specified"
        sys.exit(-1)

    if options.schema is None:
        parser.print_help()
        print "schema file must be specified"
        sys.exit(-1)

    f = open(options.schema, 'r')
    schema = f.read()
    f.close()
    
    conn = sqlite3.connect(options.db)
    conn.execute(schema)

if __name__ == '__main__':
    main()

