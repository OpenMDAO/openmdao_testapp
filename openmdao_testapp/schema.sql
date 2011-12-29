CREATE TABLE tests (
   id INTEGER PRIMARY KEY,
   commit_id TEXT,
   host TEXT,
   passes INTEGER,
   fails INTEGER,
   skips INTEGER,
   elapsed_time TEXT,
   platform TEXT,
   results BLOB,
   doc_results TEXT,
   date TEXT
);


CREATE TABLE docbuilds (
   commit_id TEXT,
   results BLOB
);

