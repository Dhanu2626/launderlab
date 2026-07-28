-- LaunderLab core banking ledger (DuckDB)

CREATE SEQUENCE IF NOT EXISTS txn_seq;

CREATE TABLE IF NOT EXISTS customers (
    customer_id   VARCHAR PRIMARY KEY,
    full_name     VARCHAR NOT NULL,
    dob           DATE,
    segment       VARCHAR NOT NULL CHECK (segment IN ('salaried','business','student','nri','merchant')),
    city          VARCHAR,
    kyc_level     VARCHAR DEFAULT 'full' CHECK (kyc_level IN ('minimal','full','enhanced')),
    risk_rating   VARCHAR DEFAULT 'low' CHECK (risk_rating IN ('low','medium','high')),
    created_at    TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id    VARCHAR PRIMARY KEY,
    customer_id   VARCHAR NOT NULL REFERENCES customers(customer_id),
    account_type  VARCHAR NOT NULL CHECK (account_type IN ('savings','current')),
    ifsc          VARCHAR NOT NULL,
    status        VARCHAR DEFAULT 'active' CHECK (status IN ('active','dormant','frozen','closed')),
    opened_at     TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    txn_id            BIGINT PRIMARY KEY DEFAULT nextval('txn_seq'),
    ts                TIMESTAMP NOT NULL,
    account_id        VARCHAR NOT NULL REFERENCES accounts(account_id),
    direction         VARCHAR NOT NULL CHECK (direction IN ('DR','CR')),
    channel           VARCHAR NOT NULL CHECK (channel IN ('UPI','NEFT','IMPS','RTGS','NACH','ATM','POS','CASH','CHQ','INT')),
    amount            DECIMAL(15,2) NOT NULL CHECK (amount > 0),
    counterparty_name VARCHAR,
    counterparty_ref  VARCHAR,
    narration         VARCHAR NOT NULL,
    balance_after     DECIMAL(15,2) NOT NULL
);

-- Ground truth: which transactions belong to an injected crime scheme.
-- The blue team must NEVER read this table; only the scorer may.
CREATE TABLE IF NOT EXISTS scheme_labels (
    txn_id     BIGINT NOT NULL REFERENCES transactions(txn_id),
    scheme_id  VARCHAR NOT NULL,
    typology   VARCHAR NOT NULL,
    role       VARCHAR,
    PRIMARY KEY (txn_id, scheme_id)
);

-- Ground truth: which customers genuinely ARE a watchlist entity.
-- Screening asks a different question from transaction monitoring ("is this the
-- listed person?" not "is this transaction crime?"), so it needs its own answer
-- key. Customers NOT in here whose names merely resemble a listed name are the
-- false-positive traps -- and the population generator produces those naturally,
-- since it draws from a small name pool. Same rule as scheme_labels: the
-- screening engine must NEVER read this; only the scorer may.
CREATE TABLE IF NOT EXISTS entity_labels (
    customer_id  VARCHAR NOT NULL REFERENCES customers(customer_id),
    list_name    VARCHAR NOT NULL,
    list_type    VARCHAR NOT NULL CHECK (list_type IN ('sanctions','pep')),
    match_kind   VARCHAR NOT NULL CHECK (match_kind IN ('exact','transliteration','initials','reordered')),
    PRIMARY KEY (customer_id, list_name)
);

CREATE SEQUENCE IF NOT EXISTS article_seq;

-- Synthetic adverse media: the unstructured signal screening has to reason about.
-- Some articles are genuinely about a listed entity, some name an unrelated person
-- who happens to share a customer's name, some are benign business news.
CREATE TABLE IF NOT EXISTS adverse_media (
    article_id      BIGINT PRIMARY KEY DEFAULT nextval('article_seq'),
    ts              TIMESTAMP NOT NULL,
    headline        VARCHAR NOT NULL,
    body            VARCHAR NOT NULL,
    mentioned_name  VARCHAR NOT NULL,
    category        VARCHAR NOT NULL
);

-- Ground truth: which article is genuinely about which customer. An article whose
-- mentioned_name matches a customer NOT linked here is a real-world false positive
-- (same name, different human). Scorer-only, like the tables above.
CREATE TABLE IF NOT EXISTS media_labels (
    article_id   BIGINT NOT NULL REFERENCES adverse_media(article_id),
    customer_id  VARCHAR NOT NULL REFERENCES customers(customer_id),
    PRIMARY KEY (article_id, customer_id)
);

CREATE INDEX IF NOT EXISTS idx_txn_account_ts ON transactions(account_id, ts);
CREATE INDEX IF NOT EXISTS idx_txn_ts ON transactions(ts);
