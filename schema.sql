CREATE TABLE IF NOT EXISTS job_skill_stats (
    job_title TEXT,
    skill TEXT,
    count INTEGER,
    percentage REAL,
    PRIMARY KEY(job_title, skill)
);

CREATE TABLE IF NOT EXISTS job_count (
    job_title TEXT,
    job_count INTEGER,
    PRIMARY KEY(job_title)
);
