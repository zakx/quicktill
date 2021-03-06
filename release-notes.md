quicktill — cash register software
==================================

Upgrade v0.11.x to v0.12
------------------------

There are major database and config file changes this release.

Update the configuration file first, followed by the database.

In the configuration file you must make the following changes:

 - Replace K_ONE, K_TWO, ... K_ZERO, K_ZEROZERO, K_POINT with "1",
   "2", ... "0", "00", "."
 - Remove all deptkey() calls; deptkeys can now be expressed as PLUs
   with no price set
 - Rewrite modifiers to use the new interface
 - Replace ord('x') with 'x' in hotkeys
 - Replace usestock_hook with a subclass of usestock.UseStockHook
 - Replace priceguess with a subclass of stocktype.PriceGuessHook
 - Remove references to curseskeyboard() - they are no longer necessary

To upgrade the database:

 - install the new release
 - run "runtill syncdb"
 - run psql and give the following commands to the database:

```
BEGIN;
-- Remove UNIQUE constraint on stockout.translineid
ALTER TABLE stockout DROP CONSTRAINT stockout_translineid_key;

-- Rename K_ONE to 1 etc. in keyboard.menukey
UPDATE keyboard SET menukey='1' WHERE menukey='K_ONE';
UPDATE keyboard SET menukey='2' WHERE menukey='K_TWO';
UPDATE keyboard SET menukey='3' WHERE menukey='K_THREE';
UPDATE keyboard SET menukey='4' WHERE menukey='K_FOUR';
UPDATE keyboard SET menukey='5' WHERE menukey='K_FIVE';
UPDATE keyboard SET menukey='6' WHERE menukey='K_SIX';
UPDATE keyboard SET menukey='7' WHERE menukey='K_SEVEN';
UPDATE keyboard SET menukey='8' WHERE menukey='K_EIGHT';
UPDATE keyboard SET menukey='9' WHERE menukey='K_NINE';
UPDATE keyboard SET menukey='0' WHERE menukey='K_ZERO';
UPDATE keyboard SET menukey='00' WHERE menukey='K_ZEROZERO';
UPDATE keyboard SET menukey='.' WHERE menukey='K_POINT';

-- Add NOT NULL constraint to transaction notes
UPDATE transactions SET notes='' WHERE notes IS NULL;
ALTER TABLE transactions ALTER COLUMN notes SET NOT NULL;

-- Add new columns to stocklines table and figure out line types
ALTER TABLE stocklines
	ADD COLUMN linetype character varying(20),
	ADD COLUMN stocktype integer,
	ALTER COLUMN dept DROP NOT NULL;

UPDATE stocklines SET linetype='regular' WHERE capacity IS NULL;
UPDATE stocklines SET linetype='display' WHERE capacity IS NOT NULL;
ALTER TABLE stocklines ALTER COLUMN linetype SET NOT NULL;
-- For display stocklines, guess the stocktype of the existing
-- display stock.  Display stocklines with no stock get a random stocktype,
-- which the user will have to change later.
UPDATE stocklines SET stocktype=(
  SELECT st.stocktype FROM stock s
    LEFT JOIN stocktypes st ON s.stocktype=st.stocktype
    WHERE stocklines.stocklineid=s.stocklineid
    LIMIT 1)
  WHERE linetype='display';
UPDATE stocklines SET stocktype=(
  SELECT stocktype FROM stocktypes LIMIT 1)
  WHERE linetype='display' AND stocktype IS NULL;
UPDATE stocklines SET dept=null WHERE linetype='display';

-- Add the saleprice_units column to stocktypes
ALTER TABLE stocktypes
        ADD COLUMN saleprice_units numeric(8,1);
UPDATE stocktypes SET saleprice_units=1.0;
ALTER TABLE stocktypes
        ALTER COLUMN saleprice_units SET NOT NULL;

COMMIT;
```

 - run "runtill checkdb", check that the output looks sensible, then
   pipe it or paste it in to psql
 - run "runtill checkdb" again and check it produces no output


Upgrade v0.10.57 to v0.11.0
---------------------------

There are major database and config file changes this release.

To upgrade the database:

 - install the new release
 - run "runtill syncdb"
 - run psql and give the following commands to the database:
```
BEGIN;
ALTER TABLE keyboard ALTER COLUMN stocklineid DROP NOT NULL;
ALTER TABLE keyboard ADD COLUMN pluid INTEGER REFERENCES pricelookups(id) ON DELETE CASCADE;
ALTER TABLE keyboard ADD COLUMN modifier VARCHAR;
ALTER TABLE keyboard ADD CONSTRAINT "be_unambiguous_constraint" CHECK (stocklineid IS NULL OR pluid IS NULL);
ALTER TABLE keyboard ADD CONSTRAINT "be_useful_constraint" CHECK (stocklineid IS NOT NULL OR pluid IS NOT NULL OR modifier IS NOT NULL);
UPDATE keyboard SET modifier='Half' WHERE qty=0.5;
UPDATE keyboard SET modifier='Double' WHERE qty=2.0;
ALTER TABLE keyboard DROP COLUMN qty;
COMMIT;
```

In the configuration file you must make the following changes:

 - remove all modkey() definitions and replace them with line keys
 - remove the pricepolicy function
 - remove the deptkeycheck function if you have not already done so
 - add definitions for all the modifier keys you plan to use; follow
   the Haymakers example config file where possible
 - change "from quicktill.plu import popup as plu" to "from
   quicktill.pricecheck import popup as plu"
