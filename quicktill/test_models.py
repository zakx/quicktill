from . import models
import unittest
import datetime
from decimal import Decimal
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

TEST_DATABASE_NAME="quicktill-test"

class ModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create the test database
        engine=create_engine("postgresql+psycopg2:///postgres")
        conn=engine.connect()
        conn.execute('commit')
        conn.execute('create database "{}"'.format(TEST_DATABASE_NAME))
        conn.close()
        cls._engine=create_engine("postgresql+psycopg2:///{}".format(
            TEST_DATABASE_NAME))
        models.metadata.bind=cls._engine
        models.metadata.create_all()
        cls._sm=sessionmaker()

    @classmethod
    def tearDownClass(cls):
        # Dispose of the connection pool, closing all checked-in connections
        cls._engine.dispose()
        del cls._engine
        engine=create_engine("postgresql+psycopg2:///postgres")
        conn=engine.connect()
        conn.execute('commit')
        conn.execute('drop database "{}"'.format(TEST_DATABASE_NAME))
        conn.close()

    def setUp(self):
        self.connection=self._engine.connect()
        self.trans=self.connection.begin()
        self.s=self._sm(bind=self.connection)

    def tearDown(self):
        self.s.close()
        self.trans.rollback()
        self.connection.close()

    def test_add_business(self):
        self.s.add(models.Business(
            id=1,name='Test',abbrev='TEST',address='An address'))
        self.s.commit()

    def test_no_current_session(self):
        current=models.Session.current(self.s)
        self.assertIsNone(current)

    def test_no_session_totals_reports_none(self):
        """
        Session.actual_total should be None for sessions with no
        totals recorded.

        """
        session=models.Session(datetime.date.today())
        self.s.add(session)
        self.s.commit()
        self.assertIsNone(session.actual_total)
        session.endtime=datetime.datetime.now()
        self.s.commit()
        self.assertIsNone(session.actual_total)

    def test_actual_session_totals(self):
        session=models.Session(datetime.date.today())
        session.endtime=datetime.datetime.now()
        cash=models.PayType(paytype='CASH',description='Cash')
        card=models.PayType(paytype='CARD',description='Card')
        self.s.add_all([session,cash,card])
        self.s.commit()
        self.s.add_all([
            models.SessionTotal(session=session,paytype=cash,amount=Decimal(2)),
            models.SessionTotal(session=session,paytype=card,amount=Decimal(1)),
            ])
        self.s.commit()
        self.assertEqual(session.actual_total,Decimal(3))

if __name__=='__main__':
    unittest.main()