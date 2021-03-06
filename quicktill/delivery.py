from . import ui, stock, td, keyboard, printer, tillconfig, stocktype
from . import user, usestock
from decimal import Decimal
from .models import Delivery, Supplier, StockUnit, StockItem, StockType
from .models import penny
from .plugins import InstancePluginMount
import datetime

import logging
log = logging.getLogger(__name__)

@user.permission_required('deliveries', "List deliveries")
def deliverymenu():
    """Display a list of deliveries and call the edit function.
    """
    dl = td.s.query(Delivery)\
             .order_by(Delivery.checked)\
             .order_by(Delivery.date.desc())\
             .order_by(Delivery.id.desc())\
             .all()
    f = ui.tableformatter(' r L l L l ')
    lines = [(f(x.id, x.supplier.name, x.date, x.docnumber or "",
                "" if x.checked else "not confirmed"),
              delivery, (x.id,)) for x in dl]
    lines.insert(0, ("Record new delivery", delivery, None))
    ui.menu(lines, title="Delivery List",
            blurb="Select a delivery and press Cash/Enter.")

class deliveryline(ui.line):
    def __init__(self, stockitem):
        ui.line.__init__(self)
        self.stockitem = stockitem
        self.update()

    def update(self):
        s = self.stockitem
        td.s.add(s)
        try:
            coststr = format(s.costprice, ">-6.2f")
        except:
            coststr = "????? "
        self.text = "%7d %-37s %-8s %s %-5.2f %-10s" % (
            s.id, s.stocktype.format(maxw=37), s.stockunit.id,
            coststr, s.stocktype.saleprice, ui.formatdate(s.bestbefore))

class delivery(ui.basicpopup):
    """Delivery popup

    The delivery window allows a delivery to be edited, printed or
    confirmed.  Prior to confirmation all details of a delivery can be
    changed.  After confirmation the delivery is read-only.  The
    window contains a header area, with supplier name, delivery date
    and document number; a couple of prompts, and a scrollable list of
    stock items.  If the window is not read-only, there is always a
    blank line at the bottom of the list to enable new entries to be
    made.

    If no delivery ID is passed, a new delivery will be created once a
    supplier has been chosen.
    """
    def __init__(self, dn=None):
        mh, mw = ui.rootwin.size()
        if mw < 80 or mh < 14:
            ui.infopopup(["Error: the screen is too small to display "
                          "the delivery dialog box.  It must be at least "
                          "80x14 characters."],
                         title="Screen width problem")
            return
        if dn:
            d = td.s.query(Delivery).get(dn)
        else:
            d = None
        if d:
            self.dl = [deliveryline(x) for x in d.items]
            self.dn = d.id
        else:
            self.dl = []
            self.dn = None
        if d and d.checked:
            title = "Delivery Details - %d - read only (already confirmed)" % d.id
            cleartext = "Press Clear to go back"
            skm = {keyboard.K_CASH: (self.view_line, None)}
            readonly = True
        else:
            title = "Delivery Details"
            if self.dn:
                title = title + " - %d" % self.dn
            cleartext = None
            skm = {keyboard.K_CASH: (self.edit_line, None),
                   keyboard.K_CANCEL: (self.deleteline, None),
                   keyboard.K_QUANTITY: (self.duplicate_item, None)}
            readonly = False
        # The window can be as tall as the screen; we expand the scrollable
        # field to fit.  The scrollable field must be at least three lines
        # high!
        ui.basicpopup.__init__(
            self, mh, 80, title=title, cleartext=cleartext,
            colour=ui.colour_input)
        if readonly:
            self.win.set_cursor(False)
        self.addstr(2, 2, "       Supplier:")
        self.addstr(3, 2, "           Date:")
        self.addstr(4, 2, "Document number:")
        self.addstr(6, 1, "StockNo Stock Type........................... "
                    "Unit.... Cost.. Sale  BestBefore")
        self.supfield = ui.modelfield(
            2, 19, 59, Supplier, 'name', default=d.supplier if d else None,
            create=createsupplier, readonly=readonly)
        # If there is not yet an underlying Delivery object, the window
        # can be dismissed by pressing Clear on the supplier field
        if self.dn is None:
            self.supfield.keymap[keyboard.K_CLEAR] = (self.dismiss, None)
        self.datefield = ui.datefield(
            3, 19, f=d.date if d else datetime.date.today(),
            readonly=readonly)
        self.docnumfield = ui.editfield(4, 19, 40, f=d.docnumber if d else "",
                                        readonly=readonly)
        self.entryprompt = None if readonly else ui.line(
            " [ New item ]")
        self.s = ui.scrollable(
            7, 1, 78, mh - 9 if readonly else mh - 10, self.dl,
            lastline=self.entryprompt, keymap=skm)
        self.addstr(mh - 2 if readonly else mh - 3, 33, "Total cost ex-VAT:")
        self.costfield = ui.label(mh - 2 if readonly else mh - 3,
                                  52, 10, align='>')
        self.update_costfield()
        if readonly:
            self.s.focus()
        else:
            self.deletefield = ui.buttonfield(
                mh - 2, 2, 24, "Delete this delivery", keymap={
                    keyboard.K_CASH: (self.confirmdelete, None)})
            self.confirmfield = ui.buttonfield(
                mh - 2, 28, 31, "Confirm details are correct", keymap={
                    keyboard.K_CASH: (self.confirmcheck, None)})
            self.savefield = ui.buttonfield(
                mh - 2, 61, 17, "Save and exit", keymap={
                    keyboard.K_CASH: (self.finish, None)})
            ui.map_fieldlist(
                [self.supfield, self.datefield, self.docnumfield, self.s,
                 self.deletefield, self.confirmfield, self.savefield])
            self.supfield.sethook = self.update_model
            self.datefield.sethook = self.update_model
            self.docnumfield.sethook = self.update_model
            if self.dn:
                self.s.focus()
            else:
                self.supfield.focus()

    def update_costfield(self):
        if self.dn:
            d = td.s.query(Delivery).get(self.dn)
            self.costfield.set(
                tillconfig.fc(d.costprice) if d.costprice else "?????")

    def update_model(self):
        # Called whenever one of the three fields at the top changes.
        # If the three fields are valid and we have a Delivery model,
        # update it.  If any of them are not valid, or there is not
        # yet a Delivery model, do nothing.
        if self.supfield.f is None:
            return
        date = self.datefield.read()
        if not date:
            return
        if self.docnumfield.f == "":
            return
        if not self.dn:
            return
        d = td.s.query(Delivery).get(self.dn)
        d.supplier = self.supfield.read()
        d.date = date
        d.docnumber = self.docnumfield.f
        td.s.flush()
        self.update_costfield()

    def make_delivery_model(self):
        # If we do not have a delivery ID, create one if possible.  If
        # we still don't have one after this, it's because a required
        # field was missing and we've just popped up an error message
        # about it.
        if self.dn:
            return
        if self.supfield.f is None:
            ui.infopopup(["Select a supplier before continuing!"], title="Error")
            return
        date = self.datefield.read()
        if date is None:
            ui.infopopup(["Check that the delivery date is correct before "
                          "continuing!"], title="Error")
            return
        if self.docnumfield.f == "":
            ui.infopopup(["Enter a document number before continuing!"],
                         title="Error")
            return
        d = Delivery()
        d.supplier = self.supfield.read()
        d.date = date
        d.docnumber = self.docnumfield.f
        td.s.add(d)
        td.s.flush()
        self.dn = d.id
        del self.supfield.keymap[keyboard.K_CLEAR]
        self.addstr(0, 1, "Delivery Details - {}".format(d.id))

    def finish(self):
        # Save and exit button
        self.make_delivery_model()
        if self.dn:
            self.dismiss()

    def reallydeleteline(self):
        item = self.dl[self.s.cursor].stockitem
        td.s.add(item)
        td.s.delete(item)
        del self.dl[self.s.cursor]
        td.s.flush()
        self.s.drawdl()
        self.update_costfield()

    def deleteline(self):
        if not self.s.cursor_on_lastline():
            td.s.add(self.dl[self.s.cursor].stockitem)
            ui.infopopup(
                ["Press Cash/Enter to confirm deletion of stock "
                 "number %d.  Note that once it's deleted you can't "
                 "create a new stock item with the same number; new "
                 "stock items always get fresh numbers." % (
                        self.dl[self.s.cursor].stockitem.id)],
                title="Confirm Delete",
                keymap={keyboard.K_CASH: (self.reallydeleteline, None, True)})

    def printout(self):
        if self.dn is None:
            return
        menu = [("Print labels on {}".format(str(x)),
                 printer.label_print_delivery,(x,self.dn))
                for x in printer.labelprinters]
        ui.automenu(menu, title="Delivery print options",
                    colour=ui.colour_confirm)

    def reallyconfirm(self):
        if not self.dn:
            return
        d = td.s.query(Delivery).get(self.dn)
        d.checked = True
        td.s.flush()
        self.dismiss()
        usestock.auto_allocate_internal(deliveryid=self.dn,
                                        message_on_no_work=False)
        for i in DeliveryHooks.instances:
            i.confirmed(self.dn)

    def confirmcheck(self):
        if not self.dn or not self.dl:
            ui.infopopup(["There is nothing here to confirm!"],
                         title="Error")
            return
        for i in DeliveryHooks.instances:
            if i.preConfirm(self.dn):
                return
        ui.infopopup(["When you confirm a delivery you are asserting that "
                      "you have received and checked every item listed as part "
                      "of the delivery.  Once the delivery is confirmed, you "
                      "can't go back and change any of the details.  Press "
                      "Cash/Enter to confirm this delivery now, or Clear to "
                      "continue editing it."], title="Confirm Details",
                     keymap={keyboard.K_CASH: (self.reallyconfirm, None, True)})

    def line_edited(self, stockitem):
        # Only called when a line has been edited; not called for new
        # lines or deletions
        self.dl[self.s.cursor].update()
        self.s.cursor_down()
        self.update_costfield()

    def newline(self, stockitem):
        self.dl.append(deliveryline(stockitem))
        self.s.cursor_down()
        self.update_costfield()

    def edit_line(self):
        # If there is not yet an underlying Delivery object, create one
        self.make_delivery_model()
        if self.dn is None:
            return # with errors already popped up
        # If it's the "lastline" then we create a new stock item
        if self.s.cursor_on_lastline():
            stockitem(self.newline, self.dn)
        else:
            td.s.add(self.dl[self.s.cursor].stockitem)
            stockitem(self.line_edited, self.dn, self.dl[self.s.cursor].stockitem)

    def view_line(self):
        # In read-only mode there is no "lastline"
        td.s.add(self.dl[self.s.cursor].stockitem)
        stock.stockinfo_popup(self.dl[self.s.cursor].stockitem.id)

    def duplicate_item(self):
        existing = self.dl[len(self.dl) - 1 if self.s.cursor_on_lastline()
                           else self.s.cursor].stockitem
        td.s.add(existing)
        # We deliberately do not copy the best-before date, because it
        # might be different on the new item.
        new = StockItem(
            delivery=existing.delivery, stocktype=existing.stocktype,
            stockunit=existing.stockunit, costprice=existing.costprice)
        td.s.add(new)
        td.s.flush()
        self.dl.append(deliveryline(new))
        self.s.cursor_down()
        self.update_costfield()

    def reallydelete(self):
        if self.dn is None:
            self.dismiss()
            return
        d = td.s.query(Delivery).get(self.dn)
        for i in d.items:
            td.s.delete(i)
        td.s.delete(d)
        self.dismiss()

    def confirmdelete(self):
        ui.infopopup(["Do you want to delete the entire delivery and all "
                      "the stock items that have been entered for it?  "
                      "Press Cancel to delete or Clear to go back."],
                     title="Confirm Delete",
                     keymap={keyboard.K_CANCEL: (self.reallydelete, None, True)})

    def keypress(self, k):
        if k == keyboard.K_PRINT:
            self.printout()
        elif k == keyboard.K_CLEAR:
            self.dismiss()

class stockitem(ui.basicpopup):
    """Create a number of stockitems, or edit a single stockitem."""

    @staticmethod
    def _null_list(query):
        return query.filter(False)

    def __init__(self, func, deliveryid, item=None):
        """If item is provided then we edit it; otherwise we create one or
        more StockItems and call func with the StockItem as an
        argument (possibly multiple times).  The StockItem we call
        func with is in the current ORM session.
        """
        self.func = func
        self.item = item
        self.deliveryid = deliveryid
        cleartext = (
            "Press Clear to exit, forgetting all changes" if item else
            "Press Clear to exit without creating a new stock item")
        ui.basicpopup.__init__(self, 13, 78, title="Stock Item",
                               cleartext=cleartext, colour=ui.colour_line)
        if item is None:
            self.addstr(2, 2, "     Number of items:")
        else:
            self.addstr(2, 2, "        Stock number: {}".format(item.id))
        self.addstr(3, 2, "          Stock type:")
        self.addstr(4, 2, "                Unit:")
        self.addstr(5, 2, " Cost price (ex VAT): {}".format(tillconfig.currency))
        self.addstr(6, 2, "Suggested sale price:")
        self.addstr(7, 2, "Sale price (inc VAT): {}".format(tillconfig.currency))
        self.addstr(7, 31 + len(tillconfig.currency), "per")
        self.addstr(8, 2, "         Best before:")
        if not item:
            self.qtyfield = ui.editfield(
                2, 24, 5, f=1,
                validate=ui.validate_positive_nonzero_int)
            self.qtyfield.sethook = self.update_suggested_price
        self.typefield = ui.modelpopupfield(
            3, 24, 52, StockType, stocktype.choose_stocktype,
            lambda si: si.format(),
            keymap={keyboard.K_CLEAR: (self.dismiss, None)})
        self.typefield.sethook = self.typefield_changed
        self.unitfield = ui.modellistfield(
            4, 24, 30, StockUnit, self._null_list, lambda x: x.name)
        self.unitfield.sethook = self.update_suggested_price
        self.costfield = ui.editfield(5, 24 + len(tillconfig.currency), 10,
                                      validate=ui.validate_float)
        self.costfield.sethook = self.update_suggested_price
        self.salefield = ui.editfield(7, 24 + len(tillconfig.currency), 6,
                                      validate=ui.validate_float)
        self.saleunitsfield = ui.editfield(7, 34 + len(tillconfig.currency)*2,
                                           6, validate=ui.validate_float)
        self.bestbeforefield = ui.datefield(8, 24)
        self.acceptbutton = ui.buttonfield(10, 28, 21, "Accept values", keymap={
                keyboard.K_CASH: (self.accept, None)})
        fieldlist = [self.typefield, self.unitfield, self.costfield,
                     self.salefield, self.saleunitsfield,
                     self.bestbeforefield, self.acceptbutton]
        if not item:
            fieldlist.insert(0, self.qtyfield)
        ui.map_fieldlist(fieldlist)
        if item:
            self.typefield.set(item.stocktype)
            self.unitfield.set(item.stockunit)
            self.costfield.set(item.costprice)
            self.salefield.set(item.stocktype.saleprice)
            self.saleunitsfield.set(item.stocktype.saleprice_units)
            self.bestbeforefield.set(item.bestbefore)
            if self.bestbeforefield.f == "":
                self.bestbeforefield.focus()
            else:
                self.acceptbutton.focus()
            self.updateunitfield()
        else:
            self.typefield.focus()

    def typefield_changed(self):
        self.updateunitfield()
        self.update_suggested_price()
        self.addstr(7, 40 + len(tillconfig.currency) * 2, ' ' * 15)
        newtype = self.typefield.read()
        if newtype:
            self.addstr(7, 41 + len(tillconfig.currency) * 2, "{}s".format(
                newtype.unit.name))
            self.salefield.set(newtype.saleprice)
            self.saleunitsfield.set(newtype.saleprice_units)
        else:
            self.salefield.set("")
            self.saleunitsfield.set("")

    def updateunitfield(self):
        stocktype = self.typefield.read()
        if stocktype == None:
            self.unitfield.change_query(self._null_list)
            return
        unit_id = stocktype.unit.id
        def unit_list(query):
            return query.filter(StockUnit.unit_id == unit_id)\
                        .order_by(StockUnit.size)
        self.unitfield.change_query(unit_list)

    def update_suggested_price(self):
        self.addstr(6, 24, ' ' * 10)
        if self.typefield.read() is None:
            return
        if self.unitfield.read() is None:
            return
        if len(self.costfield.f) == 0:
            return
        if not self.item and len(self.qtyfield.f) == 0:
            return
        if self.item:
            qty = 1
        else:
            qty = int(self.qtyfield.f)
        wholeprice = Decimal(self.costfield.f)
        g = stocktype.PriceGuessHook.guess_price(
            self.typefield.read(), self.unitfield.read(), wholeprice / qty)
        if g is not None:
            if isinstance(g, Decimal):
                g = g.quantize(penny)
                self.addstr(6, 24, tillconfig.fc(g))
            else:
                self.addstr(6, 24, g)

    def accept(self):
        if (not self.item and len(self.qtyfield.f) == 0) \
           or self.typefield.read() is None \
           or self.unitfield.read() is None \
           or len(self.salefield.f) == 0 \
           or len(self.saleunitsfield.f) == 0:
            ui.infopopup(["You have not filled in all the fields.  "
                          "The only optional fields are 'Best Before' "
                          "and 'Cost Price'."],
                         title="Error")
            return
        self.dismiss()
        if len(self.costfield.f) == 0:
            cost = None
        else:
            cost = Decimal(self.costfield.f).quantize(penny)
        saleprice = Decimal(self.salefield.f).quantize(penny)
        saleunits = Decimal(self.saleunitsfield.f)
        stocktype = self.typefield.read()
        stockunit = self.unitfield.read()
        if stocktype.saleprice != saleprice \
           or stocktype.saleprice_units != saleunits:
            stocktype.saleprice = saleprice
            stocktype.saleprice_units = saleunits
            stocktype.pricechanged = datetime.datetime.now()
        if self.item:
            td.s.add(self.item)
            self.item.stocktype = stocktype
            self.item.stockunit = stockunit
            self.item.costprice = cost
            self.item.bestbefore = self.bestbeforefield.read()
            td.s.flush()
            self.func(self.item)
        else:
            qty = int(self.qtyfield.f)
            costper = (cost/qty).quantize(penny) if cost else None
            remaining_cost = cost
            for i in range(qty):
                thiscost = remaining_cost if i == (qty - 1) else costper
                remaining_cost = remaining_cost - thiscost if cost else None
                item = StockItem()
                item.deliveryid = self.deliveryid
                item.stocktype = stocktype
                item.stockunit = stockunit
                item.costprice = thiscost
                item.bestbefore = self.bestbeforefield.read()
                td.s.add(item)
                td.s.flush()
                self.func(item)

def createsupplier(field, name):
    # Called by the select supplier field if it decides we need to create
    # a new supplier record.
    editsupplier(lambda supplier: field.set(supplier), defaultname=name)

class editsupplier(ui.basicpopup):
    @user.permission_required('edit-supplier', "Create or edit supplier details")
    def __init__(self, func, supplier=None, defaultname=None):
        if supplier:
            td.s.add(supplier)
        self.func = func
        self.sn = supplier.id if supplier else None
        ui.basicpopup.__init__(
            self, 11, 70, title="Supplier Details",
            colour=ui.colour_input, cleartext="Press Clear to go back")
        self.addstr(2, 2, "Please enter the supplier's details. You may ")
        self.addstr(3, 2, "leave the fields other than Name blank if you wish.")
        self.addstr(5, 2, "     Name:")
        self.addstr(6, 2, "Telephone:")
        self.addstr(7, 2, "    Email:")
        self.addstr(8, 2, "      Web:")
        self.namefield = ui.editfield(
            5, 13, 55, flen=60, keymap={
                keyboard.K_CLEAR: (self.dismiss, None)},
            f=supplier.name if supplier else defaultname)
        self.telfield = ui.editfield(
            6, 13, 20, f=supplier.tel if supplier else "")
        self.emailfield = ui.editfield(
            7, 13, 55, flen=60, f=supplier.email if supplier else "")
        self.webfield = ui.editfield(
            8, 13, 55, flen=120, f=supplier.web if supplier else "",
            keymap={
                keyboard.K_CASH:(self.confirmwin if supplier is None
                                 else self.confirmed, None)})
        ui.map_fieldlist([self.namefield, self.telfield, self.emailfield,
                          self.webfield])
        self.namefield.focus()

    def confirmwin(self):
        # Called when Cash/Enter is pressed on the last field, for new
        # suppliers only
        self.dismiss()
        ui.infopopup(["Press Cash/Enter to confirm new supplier details:",
                      "Name: {}".format(self.namefield.f),
                      "Telephone: {}".format(self.telfield.f),
                      "Email: {}".format(self.emailfield.f),
                      "Web: {}".format(self.webfield.f)],
                     title="Confirm New Supplier Details",
                     colour=ui.colour_input,keymap={
            keyboard.K_CASH: (self.confirmed, None, True)})

    def confirmed(self):
        if self.sn:
            supplier = td.s.query(Supplier).get(self.sn)
        else:
            supplier = Supplier()
            td.s.add(supplier)
        supplier.name = self.namefield.f.strip()
        supplier.tel = self.telfield.f.strip()
        supplier.email = self.emailfield.f.strip()
        supplier.web = self.webfield.f.strip()
        td.s.flush()
        if self.sn is not None:
            # note: if self.sn is None then the popup is dismissed in confirmwin
            self.dismiss()
        self.func(supplier)

@user.permission_required('update-supplier', 'Update supplier details')
def updatesupplier():
    log.info("Update supplier")
    sl = td.s.query(Supplier).order_by(Supplier.name).all()
    m = [(x.name, editsupplier, (lambda a:None, x)) for x in sl]
    ui.menu(m, blurb="Select a supplier from the list and press Cash/Enter.",
            title="Edit Supplier")

class DeliveryHooks(metaclass=InstancePluginMount):
    """Hooks for deliveries

    Accounting integration plugins should subclass this.  Instances of
    subclasses will be called in order of creation.
    """
    def preConfirm(self, deliveryid):
        """Called when a delivery is about to be confirmed.

        To prevent the confirmation taking place, return True.  You
        may pop up your own information box in this case.
        """
        pass
    def confirmed(self, deliveryid):
        """Called when a delivery has been confirmed."""
        pass
