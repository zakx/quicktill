"""This module is referred to by all the other modules that make up
the till software for global till configuration.  It is expected that
the local till configuration file will import this module and replace
most of the entries here.

"""

from .models import penny

configversion="tillconfig.py"

pubname="Test Pub Name"
pubnumber="07715 422132"
pubaddr=("31337 Beer Street","Burton","ZZ9 9AA")

# Test multi-character currency name... monopoly money!
currency="MPL"

hotkeys={}

all_payment_methods=[]
payment_methods=[]

def fc(a):
    """Format currency, using the configured currency symbol."""
    if a is None: return "None"
    return "%s%s"%(currency,a.quantize(penny))

def priceguess(stocktype,stockunit,cost):
    """
    Guess a suitable selling price for a new stock item.  Return a
    price, or None if there is no suitable guess available.  'cost' is
    the cost price _per stockunit_, eg. per cask for beer.

    """
    return None

# Do we print check digits on stock labels?
checkdigit_print=False
# Do we ask the user to input check digits when using stock?
checkdigit_on_usestock=False

# Hook that is called whenever an item of stock is put on sale, with
# a StockItem and StockLine as the arguments
def usestock_hook(stock,line):
    pass

database=None

firstpage=None

# Called by ui code whenever a usertoken is processed by the default
# page's hotkey handler
def usertoken_handler(t):
    pass
usertoken_listen=None
usertoken_listen_v6=None

# A function to turn off the screensaver if the screen has gone blank
def unblank_screen():
    pass

# The user ID to use for creating a page if not otherwise specified.
# An integer if present.
default_user=None

# The default options for the "exit / restart" menu.  These will go
# away, to be replaced by an empty list, once all till startup scripts
# have been updated to specify the options explicitly.
exitoptions = [
    (0, "Exit / restart till software"),
    (2, "Turn off till"),
    (3, "Reboot till"),
]
