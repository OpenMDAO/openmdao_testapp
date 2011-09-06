CREATE TABLE tests (
   id INTEGER PRIMARY KEY,
   commit_id TEXT,
   host TEXT,
   passes INTEGER,
   fails INTEGER,
   elapsed_time TEXT,
   platform TEXT,
   results TEXT,
   doc_results TEXT,
   date TEXT
);


