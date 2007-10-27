import ui,keyboard,printer,tillconfig
import HTMLParser
import urllib

### Train departures

# How to parse the live departure boards page:
#
# 1) Watch for the start of a table with attr class='arrivaltable'
# 2) Watch for the start of a tbody tag
# 3) For each tr tag, store the td tag contents
# 4) Stop when we get to the end of the tbody tag

class LDBParser(HTMLParser.HTMLParser):
    """Parse the UK National Rail Live Departure Boards web page
    to extract the table of destinations and departure times.

    """
    # Possible states:
    # 0 - waiting for start of table of class 'arrivaltable'
    # 1 - waiting for a tbody tag start
    # 2 - waiting for a tr tag start or a tbody tag end
    # 3 - waiting for a td tag start or a tr tag end
    # 4 - collecting data, waiting for a td tag end
    # 5 - finished
    def __init__(self):
        HTMLParser.HTMLParser.__init__(self)
        self.state=0
        self.tablelines=[]
        self.currentline=None
        self.currentdata=None
    def handle_starttag(self,tag,attrs):
        if self.state==0 and tag=='table' and ('class','arrivaltable') in attrs:
            self.state=1
        elif self.state==1 and tag=='tbody':
            self.state=2
        elif self.state==2 and tag=='tr':
            self.state=3
            self.currentline=[]
        elif self.state==3 and tag=='td':
            self.state=4
            self.currentdata=""
    def handle_endtag(self,tag):
        if self.state==4 and tag=='td':
            self.state=3
            self.currentline.append(self.currentdata)
        elif self.state==3 and tag=='tr':
            self.state=2
            self.tablelines.append(self.currentline)
        elif self.state==2 and tag=='tbody':
            self.state=5
    def handle_data(self,data):
        if self.state==4:
            self.currentdata=self.currentdata+data

def departurelist(name,code):
    # Retrieve the departure boards page
    try:
        f=urllib.urlopen("http://www.livedepartureboards.co.uk/ldb/sumdep.aspx?T=%s&A=1"%code)
        l=f.read()
        f.close()
    except:
        ui.infopopup(["Departure information could not be retrieved."],
                     title="Error")
        return
    # Parse it
    p=LDBParser()
    p.feed(l)
    p.close()
    # Now p.tablelines contains the data!  Format and display it.
    t=ui.table(p.tablelines)
    ll=t.format('l l l')
    ui.linepopup(ll,name,colour=ui.colour_info)

### Bar Billiards checker

class bbcheck(ui.dismisspopup):
    """Given the amount of money taken by a machine and the share of it
    retained by the supplier, print out the appropriate figures for
    the collection receipt.

    """
    def __init__(self,share=25.0):
        ui.dismisspopup.__init__(self,6,20,title="Bar Billiards check",
                                 dismiss=keyboard.K_CLEAR,
                                 colour=ui.colour_input)
        win=self.pan.window()
        win.addstr(2,2,"   Total gross:")
        win.addstr(3,2,"Supplier share:")
        km={keyboard.K_CLEAR: (self.dismiss,None,True)}
        self.grossfield=ui.editfield(win,2,18,5,validate=ui.validate_float,
                                     keymap=km)
        km={keyboard.K_CASH: (self.enter,None,False)}
        self.sharefield=ui.editfield(win,3,18,5,validate=ui.validate_float,
                                     keymap=km)
        self.sharefield.set(str(share))
        ui.map_fieldlist([self.grossfield,self.sharefield])
        self.grossfield.focus()
    def enter(self):
        pdriver=printer.driver
        try:
            grossamount=float(self.grossfield.f)
        except:
            grossamount=None
        try:
            sharepct=float(self.sharefield.f)
        except:
            sharepct=None
        if grossamount is None or sharepct is None:
            return ui.infopopup(["You must fill in both fields."],
                                title="You Muppet")
        if sharepct>=100.0 or sharepct<0.0:
            return ui.infopopup(["The supplier share is a percentage, "
                                 "and must be between 0 and 100."],
                                title="You Muppet")
        balancea=grossamount/(tillconfig.vatrate+1.0)
        vat_on_nett_take=grossamount-balancea
        supplier_share=balancea*sharepct/100.0
        brewery_share=balancea-supplier_share
        vat_on_rent=supplier_share*tillconfig.vatrate
        left_on_site=brewery_share+vat_on_nett_take-vat_on_rent
        banked=supplier_share+vat_on_rent
        pdriver.start()
        pdriver.setdefattr(font=1)
        pdriver.printline("Nett take:\t\t%s"%tillconfig.fc(grossamount))
        pdriver.printline("VAT on nett take:\t\t%s"%tillconfig.fc(vat_on_nett_take))
        pdriver.printline("Balance A/B:\t\t%s"%tillconfig.fc(balancea))
        pdriver.printline("Supplier share:\t\t%s"%tillconfig.fc(supplier_share))
        pdriver.printline("Licensee share:\t\t%s"%tillconfig.fc(brewery_share))
        pdriver.printline("VAT on rent:\t\t%s"%tillconfig.fc(vat_on_rent))
        pdriver.printline("(VAT on rent is added to")
        pdriver.printline("'banked' column and subtracted")
        pdriver.printline("from 'left on site' column.)")
        pdriver.printline("Left on site:\t\t%s"%tillconfig.fc(left_on_site))
        pdriver.printline("Banked:\t\t%s"%tillconfig.fc(banked))
        pdriver.end()
        self.dismiss()
