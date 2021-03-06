from . import models
import unittest
import datetime
from decimal import Decimal
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

TEST_DATABASE_NAME = "quicktill-test"

class ModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create the test database
        engine = create_engine("postgresql+psycopg2:///postgres")
        conn = engine.connect()
        conn.execute('commit')
        conn.execute('create database "{}"'.format(TEST_DATABASE_NAME))
        conn.close()
        cls._engine = create_engine("postgresql+psycopg2:///{}".format(
            TEST_DATABASE_NAME))
        models.metadata.bind = cls._engine
        models.metadata.create_all()
        cls._sm = sessionmaker()

    @classmethod
    def tearDownClass(cls):
        # Dispose of the connection pool, closing all checked-in connections
        cls._engine.dispose()
        del cls._engine
        engine = create_engine("postgresql+psycopg2:///postgres")
        conn = engine.connect()
        conn.execute('commit')
        conn.execute('drop database "{}"'.format(TEST_DATABASE_NAME))
        conn.close()

    def setUp(self):
        self.connection = self._engine.connect()
        self.trans = self.connection.begin()
        self.s = self._sm(bind=self.connection)

    def tearDown(self):
        self.s.close()
        self.trans.rollback()
        self.connection.close()

    def test_add_business(self):
        self.s.add(models.Business(
            id=1, name='Test', abbrev='TEST', address='An address'))
        self.s.commit()

    def test_no_current_session(self):
        current = models.Session.current(self.s)
        self.assertIsNone(current)

    def test_no_session_totals_reports_none(self):
        """Session.actual_total should be None for sessions with no totals
        recorded.
        """
        session = models.Session(datetime.date.today())
        self.s.add(session)
        self.s.commit()
        self.assertIsNone(session.actual_total)
        session.endtime = datetime.datetime.now()
        self.s.commit()
        self.assertIsNone(session.actual_total)

    def test_actual_session_totals(self):
        session = models.Session(datetime.date.today())
        session.endtime = datetime.datetime.now()
        cash = models.PayType(paytype='CASH', description='Cash')
        card = models.PayType(paytype='CARD', description='Card')
        self.s.add_all([session, cash, card])
        self.s.commit()
        self.s.add_all([
            models.SessionTotal(session=session, paytype=cash,
                                amount=Decimal(2)),
            models.SessionTotal(session=session, paytype=card,
                                amount=Decimal(1)),
            ])
        self.s.commit()
        self.assertEqual(session.actual_total, Decimal(3))

    def template_setup(self):
        """Add template data to the database to make other tests shorter.
        """
        business = models.Business(
            id=1, name='Test', abbrev='TEST', address='An address')
        vatband = models.VatBand(band='A', business=business, rate=0.2)
        dept = models.Department(id=1, description="Test", vat=vatband)
        sale = models.TransCode(code='S', description='Sale')
        void = models.TransCode(code='V', description='Void')
        self.s.add_all([business, vatband, dept, sale, void])
        self.s.commit()

    def template_stocktype_setup(self):
        """Add a stocktype to the database to make other tests shorter."""
        pint = models.UnitType(id='pt', name='pint')
        beer = models.StockType(
            manufacturer="A Brewery", name="A Beer", shortname="A Beer",
            abv=5, unit=pint, dept_id=1)
        self.s.add(beer)
        self.s.commit()
        return beer

    def template_stockline_and_plu_setup(self):
        self.template_setup()
        stockline = models.StockLine(name="Test SL", location="Test",
                                     linetype="regular", dept_id=1)
        plu = models.PriceLookup(description="Test PLU", note="", dept_id=1,
                                 price=1.00)
        self.s.add_all([stockline, plu])
        self.s.commit()
        return stockline, plu

    def test_stockline_linetype_constraint(self):
        self.template_setup()
        self.s.add(models.StockLine(
            name="Test", location="Test", linetype="unknown"))
        with self.assertRaises(IntegrityError):
            self.s.commit()

    def test_regular_stockline_capacity_constraint(self):
        self.template_setup()
        # Try it with a capacity
        self.s.add(models.StockLine(
            name="Test", location="Test", linetype="regular", dept_id=1,
            capacity=10, pullthru=1))
        with self.assertRaises(IntegrityError):
            self.s.commit()

    def test_regular_stockline_stocktype_constraint(self):
        self.template_setup()
        beer = self.template_stocktype_setup()
        # Try it with a stocktype
        self.s.add(models.StockLine(
            name="Test", location="Test", linetype="regular", dept_id=1,
            stocktype=beer, pullthru=1))
        self.s.commit()

    def test_display_stockline_pullthru_constraint(self):
        self.template_setup()
        beer = self.template_stocktype_setup()
        # Try it with a pullthru
        self.s.add(models.StockLine(
            name="Test", location="Test", linetype="display",
            capacity=10, pullthru=1, stocktype=beer))
        with self.assertRaises(IntegrityError):
            self.s.commit()

    def test_display_stockline_capacity_constraint(self):
        self.template_setup()
        beer = self.template_stocktype_setup()
        # Try it without a capacity
        self.s.add(models.StockLine(
            name="Test", location="Test", linetype="display",
            stocktype=beer))
        with self.assertRaises(IntegrityError):
            self.s.commit()

    def test_display_stockline_stocktype_constraint(self):
        self.template_setup()
        # Try it without a stocktype
        self.s.add(models.StockLine(
            name="Test", location="Test", linetype="display",
            capacity=10))
        with self.assertRaises(IntegrityError):
            self.s.commit()

    def test_continuous_stockline_constraint(self):
        self.template_setup()
        self.s.add(models.StockLine(
            name="Test", location="Test", linetype="continuous"))
        with self.assertRaises(IntegrityError):
            self.s.commit()

    def test_keyboard_binding_unambigous_constraint(self):
        stockline, plu=self.template_stockline_and_plu_setup()
        self.s.add(models.KeyboardBinding(
            keycode='FOO', menukey='BAR',
            stockline=stockline, plu=plu))
        with self.assertRaises(IntegrityError):
            self.s.commit()

    def test_keyboard_binding_useful_constraint(self):
        self.s.add(models.KeyboardBinding(
            keycode='FOO', menukey='BAR'))
        with self.assertRaises(IntegrityError):
            self.s.commit()

    def test_transline_void(self):
        self.template_setup()
        session = models.Session(datetime.date.today())
        self.s.add(session)
        self.s.commit()
        trans = models.Transaction(session=session)
        transline = models.Transline(
            transaction=trans, items=1,
            amount=Decimal("10.00"), dept_id=1,
            transcode='S', text="Test sale")
        self.s.add(transline)
        self.s.commit()
        self.assertEqual(trans.balance, Decimal("10.00"))
        void = transline.void(trans, None)
        self.s.add(void)
        self.s.commit()
        self.assertEqual(transline.voided_by_id, void.id)
        self.assertEqual(trans.balance, Decimal("0.00"))
        self.s.delete(void)
        self.s.commit()
        self.assertIsNone(transline.voided_by_id)
        self.assertEqual(trans.balance, Decimal("10.00"))

    def test_delivery_costprice(self):
        self.template_setup()
        beer = self.template_stocktype_setup()
        firkin = models.StockUnit(
            id='firkin', name='Firkin', size=72, unit_id='pt')
        delivery = models.Delivery(
            date=datetime.date.today(),
            supplier=models.Supplier(name="Test supplier"),
            docnumber="test")
        self.s.add(delivery)
        self.s.commit()
        self.assertIsNone(delivery.costprice)
        self.s.add(models.StockItem(
            delivery=delivery,
            stocktype=beer,
            stockunit=firkin,
            costprice=72))
        self.s.commit()
        self.assertEqual(delivery.costprice, Decimal("72.00"))
        self.s.add(models.StockItem(
            delivery=delivery,
            stocktype=beer,
            stockunit=firkin))
        self.s.commit()
        self.assertIsNone(delivery.costprice)

if __name__ == '__main__':
    unittest.main()
