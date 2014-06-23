/* This script should be run in psql when updating a database for use
with the sqlalchemy ORM based till client */

/* Replace the data integrity rules with triggers */

DROP RULE IF EXISTS max_one_open ON sessions;
CREATE OR REPLACE FUNCTION check_max_one_session_open() RETURNS trigger AS $$
BEGIN
  IF (SELECT count(*) FROM sessions WHERE endtime IS NULL)>1 THEN
    RAISE EXCEPTION 'there is already an open session';
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER max_one_session_open
  AFTER INSERT OR UPDATE ON sessions
  FOR EACH ROW EXECUTE PROCEDURE check_max_one_session_open();

DROP RULE IF EXISTS may_not_change ON sessions;

DROP RULE IF EXISTS may_not_reopen ON transactions;

DROP RULE IF EXISTS close_only_if_balanced ON transactions;

CREATE OR REPLACE FUNCTION check_transaction_balances() RETURNS trigger AS $$
BEGIN
  IF NEW.closed=true
    AND (SELECT sum(amount*items) FROM translines
      WHERE transid=NEW.transid)!=
      (SELECT sum(amount) FROM payments WHERE transid=NEW.transid)
  THEN RAISE EXCEPTION 'transaction % does not balance', NEW.transid;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER close_only_if_balanced
  AFTER INSERT OR UPDATE ON transactions
  FOR EACH ROW EXECUTE PROCEDURE check_transaction_balances();

DROP RULE IF EXISTS close_only_if_nonzero ON transactions;

DROP RULE IF EXISTS create_only_if_session_open ON transactions;

DROP RULE IF EXISTS no_add_to_closed ON payments;

CREATE OR REPLACE FUNCTION check_modify_closed_trans_payment() RETURNS trigger AS $$
BEGIN
  IF (SELECT closed FROM transactions WHERE transid=NEW.transid)=true
  THEN RAISE EXCEPTION 'attempt to modify closed transaction % payment', NEW.transid;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER no_modify_closed
  AFTER INSERT OR UPDATE ON payments
  FOR EACH ROW EXECUTE PROCEDURE check_modify_closed_trans_payment();

DROP RULE IF EXISTS no_add_to_closed ON translines;

CREATE FUNCTION check_modify_closed_trans_line() RETURNS trigger AS $$
BEGIN
  IF (SELECT closed FROM transactions WHERE transid=NEW.transid)=true
  THEN RAISE EXCEPTION 'attempt to modify closed transaction % line', NEW.transid;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER no_modify_closed
  AFTER INSERT OR UPDATE ON translines
  FOR EACH ROW EXECUTE PROCEDURE check_modify_closed_trans_line();

/* stockonsale table is now merged with stock */

ALTER TABLE stock ADD COLUMN stocklineid INT REFERENCES stocklines(stocklineid)
  ON DELETE SET NULL;
ALTER TABLE stock ADD COLUMN displayqty INT;
ALTER TABLE stock ADD CONSTRAINT displayqty_null_if_no_stockline
  CHECK (not(stocklineid is null) or displayqty is null);

UPDATE stock SET stocklineid=sos.stocklineid,displayqty=sos.displayqty
  FROM stock s LEFT JOIN stockonsale sos ON s.stockid=sos.stockid
  WHERE stock.stockid=s.stockid;

CREATE OR REPLACE RULE log_stocktype AS ON UPDATE TO stock
  WHERE NEW.stocklineid is not null
  DO ALSO
  INSERT INTO stockline_stocktype_log VALUES
  (NEW.stocklineid,NEW.stocktype);

/* This rule is possible even without removing stockonsale */
ALTER TABLE stock ADD CONSTRAINT finished_and_finishcode_null_together
  CHECK ((finished IS NULL)=(finishcode IS NULL));

/* This rule only works once stockonsale and stock are merged.  It
could be written without the double-negative but then it is less
obvious that it is "not-null finished implies stocklineid is null". */
ALTER TABLE stock ADD CONSTRAINT stockline_null_if_finished
  CHECK (NOT(finished IS NOT NULL) OR stocklineid IS NULL);

DROP TABLE stockonsale;

/* The "stockref" field on translines is redundant.  It's much better
just to see which stockout row points at a particular transline.  We
need a 'unique' constraint on stockout.translineid too, and we have to
put back the foreign key constraint we left out in the original
schema! */

ALTER TABLE translines DROP COLUMN stockref;

/* Some existing databases have dangling references from
stockout.translineid - these seem to be to do with manually-performed
voids.  Set these to null instead. */
UPDATE stockout SET translineid=null WHERE stockoutid IN
  (SELECT stockoutid FROM stockout so
    LEFT JOIN translines tl ON so.translineid=tl.translineid
    WHERE tl.translineid is null AND so.translineid IS NOT NULL);

DROP INDEX IF EXISTS stockout_translineid_key;
ALTER TABLE stockout
  ADD CONSTRAINT stockout_translineid_key
  UNIQUE (translineid);

ALTER TABLE stockout
  ADD CONSTRAINT stockout_translineid_fkey
  FOREIGN KEY (translineid) REFERENCES translines(translineid)
  ON DELETE CASCADE;

/* The various views defined in the createdb script are no longer
used. */
DROP VIEW stockinfo;
DROP VIEW stockqty;
DROP VIEW businesstotals;

/* Saleprice has moved from stock to stocktypes.  Since prices tend
only to go up, use the maximum saleprice when migrating! */
ALTER TABLE stocktypes ADD COLUMN saleprice NUMERIC(5,2);
ALTER TABLE stocktypes ADD COLUMN pricechanged TIMESTAMP;

UPDATE stocktypes st SET saleprice=(
  SELECT max(saleprice) FROM stock
  WHERE stock.stocktype=st.stocktype);

ALTER TABLE stock DROP COLUMN saleprice;

/* Keyboard bindings need a foreign key constraint on stocklines */
ALTER TABLE keyboard
  ADD CONSTRAINT keyboard_stocklineid_fkey
  FOREIGN KEY (stocklineid) REFERENCES stocklines(stocklineid)
  ON DELETE CASCADE;

/* The quantity in keyboard bindings should have a single decimal place */
ALTER TABLE keyboard
  ALTER COLUMN qty SET DATA TYPE NUMERIC(5,1);


/* We are getting rid of the idea of different keyboard layouts in the
   database.  Installations with multiple keyboards will use different
   line numbers.  Make sure the primary keyboard is set to layout
   number 1! */

DELETE FROM keyboard WHERE layout!=1;
ALTER TABLE keyboard DROP COLUMN layout; /* Drops primary key */
ALTER TABLE keyboard ADD PRIMARY KEY (keycode,menukey);
DELETE FROM keycaps WHERE layout!=1;
ALTER TABLE keycaps DROP COLUMN layout; /* Drops primary key */
ALTER TABLE keycaps ADD PRIMARY KEY (keycode);

/* Move the old users table out of the way */
DROP TABLE users;

/* Create the new users table here - although it would be created by
syncdb, we need to refer to it when we create the user foreign key
relationship on translines and payments.  We don't need to create the
permissions or permission grants tables here. */
CREATE SEQUENCE user_seq START WITH 1;
CREATE TABLE users (
       id INTEGER NOT NULL PRIMARY KEY,
       fullname VARCHAR NOT NULL,
       shortname VARCHAR NOT NULL,
       webuser VARCHAR UNIQUE,
       enabled BOOLEAN NOT NULL,
       superuser BOOLEAN NOT NULL,
       transid INTEGER REFERENCES transactions(transid) ON DELETE SET NULL,
       register VARCHAR );

ALTER TABLE translines DROP COLUMN source;
ALTER TABLE translines ADD COLUMN "user" INTEGER REFERENCES users(id);
ALTER TABLE payments ADD COLUMN "user" INTEGER REFERENCES users(id);

/* Add the new fields to the Department table */
ALTER TABLE departments ADD COLUMN notes TEXT;
ALTER TABLE departments ADD COLUMN minprice NUMERIC(5,2);
ALTER TABLE departments ADD COLUMN maxprice NUMERIC(5,2);

ALTER TABLE stock_annotations ADD COLUMN "user" INTEGER REFERENCES users(id);

/* Alter and update the Business table */
ALTER TABLE businesses
  ALTER COLUMN address SET DATA TYPE VARCHAR;
ALTER TABLE businesses ALTER COLUMN name SET NOT NULL;
ALTER TABLE businesses ALTER COLUMN abbrev SET NOT NULL;
ALTER TABLE businesses ALTER COLUMN address SET NOT NULL;
ALTER TABLE businesses ADD COLUMN show_vat_breakdown BOOLEAN NOT NULL DEFAULT false;