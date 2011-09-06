"""
Creates a new testing database
"""

import os
import sys
import sqlite3
from optparse import OptionParser

def main():
    parser = OptionParser()
    parser.add_option("-s", "--schema", action="store", type="string", 
                      dest='schema', default='schema.sql',
                      help='schema file')
    parser.add_option("-d", "--db", action="store", type="string", 
                      dest='db', default='testdb',
                      help="db file to be created")
    
    (options, args) = parser.parse_args(sys.argv[1:])

    if options.db is None:
        parser.print_help()
        print "db file must be specified"
        sys.exit(-1)
    elif os.path.exists(options.db):
        print 'db file %s already exists' % options.db
        sys.exit(-1)

    if options.schema is None:
        parser.print_help()
        print "schema file must be specified"
        sys.exit(-1)
    elif not os.path.exists(options.schema):
        print "schema file %s doesn't exist" % options.schema
        sys.exit(-1)

    f = open(options.schema, 'r')
    schema = f.read()
    f.close()
    
    conn = sqlite3.connect(options.db)
    conn.execute(schema)

if __name__ == '__main__':
    main()

