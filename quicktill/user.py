"""Users and permissions.

For each user we store a set of strings which correspond to the
actions that user is allowed to perform.  We also support the
definition of "groups" which are themselves sets of strings
corresponding to actions.

We maintain a dictionary in which we can look up descriptions of
actions that are collected from the places these actions are used.
The dictionary stores the first description it sees for each action;
the assumption is that old descriptions loaded from the database will
be superseded by descriptions from the code, which will be seen first.

This module provides a class to derive from (permission_checked) and a
function decorator (permission_required) for other modules to use to
indicate restricted functionality.
"""

from . import ui, td, keyboard, tillconfig, cmdline
from .models import User, UserToken, Permission
from sqlalchemy.orm import joinedload
import types
import socket
import logging
import datetime
import collections
log = logging.getLogger(__name__)

class ActionDescriptionRegistry(dict):
    def __getitem__(self, key):
        if key in self:
            return dict.__getitem__(self, key)
        else:
            return "undefined"

    def __setitem__(self, key, val):
        if key in self:
            return
        if val is None:
            return
        dict.__setitem__(self, key, val)

action_descriptions = ActionDescriptionRegistry()

class _permission_checked_metaclass(type):
    """Metaclass for permission_checked classes."""
    def __new__(meta, name, bases, dct):
        # Called when a permission_checked class is defined.  Look at
        # the permission_required and register its action description.
        pr = dct.get("permission_required")
        if pr:
            action_descriptions[pr[0]] = pr[1]
        return type.__new__(meta, name, bases, dct)

    def __call__(cls, *args, **kwargs):
        # Called when a permission_checked class is about to be
        # instantiated
        u = ui.current_user()
        if cls.allowed(u):
            return type.__call__(cls, *args, **kwargs)
        else:
            if u:
                ui.infopopup(
                    ["{user} does not have the '{req}' permission "
                     "which is required for this operation.".format(
                            user=u.fullname, req=cls.permission_required[0])],
                    title="Not allowed")
            else:
                ui.infopopup(
                    ["This operation needs the '{req}' permission, "
                     "but there is no current user.".format(
                            req=cls.permission_required[0])],
                    title="Not allowed")

class permission_checked(object, metaclass=_permission_checked_metaclass):
    """Base class for restricted access classes

    Inherit from this class if you want your class to check
    permissions before allowing itself to be initialised.

    Set permission_required = (action, description) in your class to
    describe the permission required.
    """
    @classmethod
    def allowed(cls, user=None):
        """Check permission

        Can the specified user (or the current user if None) do this
        thing?
        """
        user = user or ui.current_user()
        if user is None:
            return False
        return user.may(cls.permission_required[0])

class permission_required:
    """Function decorator to perform permission check

    A factory that creates decorators that will perform a permission
    check on the current user before permitting the call.

    Use as follows:
    @permission_required('test', 'Perform tests')
    def do_test(...):
        pass

    Don't use this on the __init__ method of classes; subclass
    permission_checked and set the permission_required class attribute
    instead.  It's ok to use this on other methods of classes.
    """
    def __init__(self, action, description=None):
        self._action = action
        self._description = description
        if description:
            action_descriptions[action] = description

    def __call__(self, function):
        """Decorate a function to perform the permission check"""
        def allowed(user=None):
            user = user or ui.current_user()
            if user is None:
                return False
            return user.may(self._action)

        def permission_check(*args, **kwargs):
            if allowed():
                return function(*args, **kwargs)
            else:
                u = ui.current_user()
                if u:
                    ui.infopopup(
                        ["{user} does not have the '{req}' permission "
                         "which is required for this operation.".format(
                             user=u.fullname, req=self._action)],
                        title="Not allowed")
                else:
                    ui.infopopup(
                        ["This operation needs the '{req}' permission, "
                         "but there is no current user.".format(
                             req=self._action)],
                        title="Not allowed")
        permission_check.allowed = allowed
        return permission_check

class group:
    """A group of permissions.

    Groups always store their contents as a set, even if they are
    passed other groups.  Groups cannot refer to themselves.
    """
    all_groups = {}

    def __new__(cls, name, *args, **kwargs):
        # Prevent creation of multiple groups with the same name -
        # merge them instead.
        if name in group.all_groups:
            return group.all_groups[name]
        self = object.__new__(cls)
        group.all_groups[name] = self
        return self

    def __init__(self, name, description, members=[]):
        action_descriptions[name] = description
        self.name = name
        if not hasattr(self, 'members'):
            self.members = set()
        for m in members:
            if m in group.all_groups:
                self.members.update(group.all_groups[m].members)
            else:
                self.members.add(m)

def current_dbuser():
    user = ui.current_user()
    if user and hasattr(user, 'dbuser'):
        return user.dbuser

class built_in_user:
    """A user not present in the database

    A user defined in the configuration file.  Usually applied to a
    built-in page.

    permissions is a list of strings.  It's stored as-is for
    reference, and also flattened into a set for lookup purposes.
    """
    def __init__(self, fullname, shortname, permissions=[], is_superuser=False):
        self.fullname = fullname
        self.shortname = shortname
        self.permissions = permissions
        self.is_superuser = is_superuser
        self._flat_permissions = set()
        for m in permissions:
            if m in group.all_groups:
                self._flat_permissions.update(group.all_groups[m].members)
            else:
                self._flat_permissions.add(m)

    def may(self, action):
        """May this user perform the specified action?

        Superusers can do anything!
        """
        if self.is_superuser:
            return True
        return action in self._flat_permissions

    def has_permission(self,action):
        """Does this user have the specified permission?

        This ignores the superuser flag.
        """
        return action in self._flat_permissions

    @property
    def all_permissions(self):
        return list(self._flat_permissions)

    def display_info(self):
        def pl_display(perm):
            pl = sorted(perm)
            if pl:
                return ["  {0} ({1})".format(
                    x, action_descriptions[x]) for x in pl]
            else:
                return ["  (None)"]
        info = ["Full name: {}".format(self.fullname),
                "Short name: {}".format(self.shortname),""]
        if self.is_superuser:
            info.append("Has all permissions.")
        else:
            info = info + ["Explicit permissions:"]\
                   + pl_display(self.permissions)\
                   + ["", "All permissions:"]\
                   + pl_display(self._flat_permissions)
        ui.infopopup(info, title="{} user information".format(self.fullname),
                     colour=ui.colour_info)

class database_user(built_in_user):
    """A user loaded from the database.

    register pages require these, because they use the userid
    attribute to distinguish between different users.
    """
    def __init__(self, user):
        self.userid = user.id
        self.dbuser = user
        built_in_user.__init__(self, user.fullname, user.shortname,
                               permissions=[p.id for p in user.permissions],
                               is_superuser=user.superuser)

def load_user(userid):
    """Load the specified user from the database

    Load the specified user from the database and return a user object
    for them.  If the user does not exist or is not active, return
    None.
    """
    if not userid:
        return
    dbuser = td.s.query(User).get(userid)
    if not dbuser or not dbuser.enabled:
        return
    return database_user(dbuser)

class token:
    """A user token

    A token presented by a user at the terminal.  Usually passed to
    ui.handle_keyboard_input()
    """
    def __init__(self, t):
        self.usertoken = t
    def __eq__(self, other):
        if not isinstance(other, token):
            return False
        return self.usertoken == other.usertoken
    def __hash__(self):
        return hash(self.usertoken)
    def __repr__(self):
        return "token('{}')".format(self.usertoken)

class tokenkey(token):
    """A key that represents a user token
    """
    def __init__(self, t, label):
        super().__init__(t)
        self.keycap = label

    def __str__(self):
        return self.keycap

class tokenlistener:
    def __init__(self, address, addressfamily=socket.AF_INET):
        self.s = socket.socket(addressfamily, socket.SOCK_DGRAM)
        self.s.bind(address)
        self.s.setblocking(0)
        tillconfig.mainloop.add_fd(self.s.fileno(), self.doread,
                                   desc="token listener")

    def doread(self):
        d = self.s.recv(1024).strip().decode("utf-8")
        log.debug("Received: {}".format(repr(d)))
        if d:
            tillconfig.unblank_screen()
            with td.orm_session():
                ui.handle_keyboard_input(token(d))

def user_from_token(t):
    """Find a user given a token object.
    """
    dbt = td.s.query(UserToken)\
              .options(joinedload('user'),
                       joinedload('user.permissions'))\
              .get(t.usertoken)
    if not dbt:
        ui.toast("User token '{}' not recognised.".format(t.usertoken))
        return
    dbt.last_seen = datetime.datetime.now()
    u = dbt.user
    if not u.enabled:
        ui.toast("User '{}' is not active.".format(u.fullname))
        return
    return database_user(u)

# Here is the user interface for adding, editing and deleting users.
class adduser(permission_checked, ui.dismisspopup):
    permission_required = ('edit-user', 'Edit a user')

    def __init__(self):
        ui.dismisspopup.__init__(self, 6, 60, title="Add user",
                                 colour=ui.colour_input)
        self.addstr(2, 2, ' Full name:')
        self.addstr(3, 2, 'Short name:')
        self.fullnamefield = ui.editfield(2, 14, 40, keymap={
            keyboard.K_CLEAR: (self.dismiss, None)})
        self.shortnamefield = ui.editfield(3, 14, 30, keymap={
            keyboard.K_CASH: (self.enter, None)})
        ui.map_fieldlist([self.fullnamefield, self.shortnamefield])
        self.fullnamefield.focus()

    def enter(self):
        if not self.fullnamefield.f:
            ui.infopopup(["You must provide a full name."], title="Error")
            return
        if not self.shortnamefield.f:
            ui.infopopup(["You must provide a short name."], title="Error")
            return
        u = User(fullname=self.fullnamefield.f.strip(),
                 shortname=self.shortnamefield.f.strip(),
                 enabled=True)
        td.s.add(u)
        td.s.flush()
        self.dismiss()
        edituser(u.id)

class tokenfield(ui.ignore_hotkeys, ui.valuefield):
    emptymessage = "Use a token to fill in this field"
    def __init__(self, y, x, w, allow_inuse=False, keymap={}):
        self.y = y
        self.x = x
        self.w = w
        self.message = self.emptymessage
        self.f = None
        self._allow_inuse = allow_inuse
        super().__init__(keymap)
        self.draw()

    def set(self, t):
        if t is None:
            self.f = None
            self.message = self.emptymessage
        else:
            dbt = td.s.query(UserToken).get(t)
            if dbt and not self._allow_inuse:
                self.message = "In use by {}".format(
                    dbt.user.fullname)
                self.f = None
            else:
                self.f = t
        self.sethook()
        self.draw()

    def draw(self):
        pos = self.win.getyx()
        self.win.addstr(self.y, self.x, ' ' * self.w,
                        self.win.colour.reversed)
        if self.f:
            self.win.addstr(self.y, self.x, self.f[:self.w],
                            self.win.colour.reversed)
        else:
            if self.focused:
                self.win.addstr(self.y, self.x, self.message[:self.w],
                                self.win.colour.reversed)
        if self.focused:
            self.win.move(self.y, self.x)
        else:
            self.win.move(*pos)

    def focus(self):
        super().focus()
        self.draw()

    def defocus(self):
        super().defocus()
        self.message = self.emptymessage
        self.draw()

    def keypress(self, k):
        if hasattr(k, 'usertoken'):
            self.set(k.usertoken)
        elif k == keyboard.K_CLEAR and (
                self.f is not None or self.message != self.emptymessage):
            self.set(None)
        else:
            super().keypress(k)

class addtoken(ui.dismisspopup):
    def __init__(self, userid):
        self.userid = userid
        u = td.s.query(User).get(userid)
        ui.dismisspopup.__init__(self, 6, 66, title="Add token for {}".format(
            u.fullname), colour=ui.colour_input)
        self.addstr(2, 2, 'Description:')
        self.addstr(3, 2, '      Token:')
        self.descfield = ui.editfield(2, 20, 40, keymap={
            keyboard.K_CLEAR: (self.dismiss, None)})
        self.tokenfield = tokenfield(3, 20, 40, keymap={
            keyboard.K_CASH: (self.save, None)})
        ui.map_fieldlist([self.descfield, self.tokenfield])
        self.descfield.focus()

    def save(self):
        desc = self.descfield.f.strip()
        if len(desc) == 0 or self.tokenfield.f is None:
            ui.infopopup(["You must fill in both fields."], title="Error")
            return
        u = td.s.query(User).get(self.userid)
        t = UserToken(token=self.tokenfield.f, description=desc)
        u.tokens.append(t)
        td.s.flush()
        self.dismiss()

def do_add_permission(userid, permission):
    u = td.s.query(User).get(userid)
    p = Permission(id=permission, description=action_descriptions[permission])
    p = td.s.merge(p)
    u.permissions.append(p)
    td.s.flush()

def addpermission(userid):
    """Add a permission to a user.

    Displays a list of all available permissions.
    """
    cu = ui.current_user()
    if cu.is_superuser:
        pl = list(action_descriptions.keys())
    else:
        pl = cu.all_permissions
    # Add in groups if the list of permissions includes everything in that group
    for g in group.all_groups:
        for m in group.all_groups[g].members:
            if m not in pl:
                break
        else: # else on a for loop is skipped if the loop was exited with break
            pl.append(g)
    # Remove permissions the user already has
    u = td.s.query(User).get(userid)
    existing = [p.id for p in u.permissions]
    pl = [p for p in pl if p not in existing]
    # Generally most users will be given group permissions, so we want
    # to sort the groups to the top of the list.
    pl = sorted(pl)
    pl = sorted(pl, key=lambda p: p not in group.all_groups)
    f = ui.tableformatter(' l l ')
    menu = [(f(p, action_descriptions[p]),
             do_add_permission, (userid, p)) for p in pl]
    ui.menu(menu, title="Give permission to {}".format(u.fullname),
            blurb="Choose the permission to give to {}".format(u.fullname))

class edituser(permission_checked, ui.basicpopup):
    permission_required = ('edit-user', 'Edit a user')

    def __init__(self, userid):
        self.userid = userid
        u = td.s.query(User).get(userid)
        if u.superuser and not ui.current_user().is_superuser:
            ui.infopopup(["You can't edit {} because that user has the "
                          "superuser bit set and you do not.".format(
                              u.fullname)], title="Not allowed")
            return
        ui.basicpopup.__init__(self, 12, 60, title="Edit user",
                               colour=ui.colour_input)
        self.addstr(2, 2, '   Full name:')
        self.addstr(3, 2, '  Short name:')
        self.addstr(4, 2, 'Web username:')
        self.addstr(5, 2, '      Active:')
        self.fnfield = ui.editfield(2, 16, 40, f=u.fullname)
        self.snfield = ui.editfield(3, 16, 30, f=u.shortname)
        self.wnfield = ui.editfield(4, 16, 30, f=u.webuser)
        self.actfield = ui.booleanfield(5, 16, f=u.enabled, allow_blank=False)
        self.tokenfield = ui.buttonfield(7, 7, 15, "Edit tokens", keymap={
            keyboard.K_CASH: (self.edittokens, None)})
        self.permfield = ui.buttonfield(7, 30, 20, "Edit permissions", keymap={
            keyboard.K_CASH: (self.editpermissions, None)})
        self.savefield = ui.buttonfield(9, 6, 17, "Save and exit", keymap={
            keyboard.K_CASH: (self.save, None)})
        self.exitfield = ui.buttonfield(
            9, 29, 23, "Exit without saving", keymap={
                keyboard.K_CASH: (self.dismiss, None)})
        fl = [self.fnfield, self.snfield, self.wnfield, self.actfield,
              self.tokenfield, self.permfield, self.savefield, self.exitfield]
        if u.superuser and ui.current_user().is_superuser:
            fl.append(ui.buttonfield(
                5, 25, 30, "Remove superuser privilege", keymap={
                    keyboard.K_CASH: (self.remove_superuser, None)}))
        ui.map_fieldlist(fl)
        self.tokenfield.focus()

    def remove_superuser(self):
        self.dismiss()
        u = td.s.query(User).get(self.userid)
        u.superuser = False

    def removetoken(self, token):
        t = td.s.query(UserToken).get(token)
        td.s.delete(t)

    def edittokens(self):
        u = td.s.query(User).get(self.userid)
        f = ui.tableformatter(' l l l ')
        h = f("Description", "Value", "Last used")
        tl = [(f(x.description, x.token, x.last_seen),
               self.removetoken, (x.token,)) for x in u.tokens]
        tl.insert(0, ("Add new token", addtoken, (self.userid,)))
        ui.menu(tl, title="Tokens for {}".format(u.fullname),
                blurb=["Select a token and press Cash/Enter to remove it.",
                       "", h])

    def removepermission(self, permission):
        u = td.s.query(User).get(self.userid)
        p = td.s.query(Permission).get(permission)
        u.permissions.remove(p)

    def editpermissions(self):
        u = td.s.query(User).get(self.userid)
        f = ui.tableformatter(' l l ')
        pl = [(f(p.id, p.description),
               self.removepermission, (p.id,)) for p in u.permissions]
        pl.insert(0, ("Add permission", addpermission, (self.userid,)))
        ui.menu(pl, title="Permissions for {}".format(u.fullname),
                blurb="Select a permission and press Cash/Enter to remove it.")

    def save(self):
        fn = self.fnfield.f.strip()
        sn = self.snfield.f.strip()
        wn = self.wnfield.f.strip()
        if len(fn) == 0 or len(sn) == 0:
            ui.infopopup(["You can't leave the full name or short name blank."],
                         title="Error")
            return
        u = td.s.query(User).get(self.userid)
        u.fullname = fn
        u.shortname = sn
        u.webuser = wn if len(wn) > 0 else None
        u.enabled = self.actfield.read()
        self.dismiss()

def display_info(userid=None):
    if userid is None:
        u = ui.current_user()
        if u:
            u.display_info()
        else:
            ui.infopopup(["There is no current user."], title="User info",
                         colour=ui.colour_info)
    else:
        u = database_user(td.s.query(User).get(userid))
        u.display_info()

def usersmenu():
    """Create and edit users and tokens
    """
    ui.keymenu([
        ("1", "Users", manageusers, None),
        ("2", "Tokens", managetokens, None),
        ("3", "Current user information", display_info, None),
        ], title="Manage Users")

@permission_required("list-users", "List till users")
def manageusers(include_inactive=False):
    """List, create and edit users.
    """
    q = td.s.query(User).order_by(User.fullname)
    if not include_inactive:
        q = q.filter(User.enabled == True)
    ul = q.all()
    # There is guaranteed to be a current user because the
    # permission_required() check will have passed to get here
    u = ui.current_user()
    may_edit = u.may('edit-user')
    f = ui.tableformatter(' l l l ')
    lines = [(f(x.fullname, x.shortname,
                "(Active)" if x.enabled else "(Inactive)"),
              edituser if may_edit else display_info, (x.id,)) for x in ul]
    if not include_inactive:
        lines.insert(0, ("Include inactive users", manageusers, (True,)))
    if u.may('edit-user'):
        lines.insert(0, ("Add new user", adduser, None))
    ui.menu(lines, title="User list",
            blurb="Select a user and press Cash/Enter")

class managetokens(permission_checked, ui.dismisspopup):
    permission_required = ("manage-tokens", "Manage user login tokens")
    def __init__(self):
        ui.dismisspopup.__init__(self, 11, 60, title="Manage tokens",
                                 colour=ui.colour_input)
        self.addstr(2, 2, "      Token:")
        self.addstr(3, 2, "Description:")
        self.addstr(4, 2, "Assigned to:")
        self.addstr(5, 2, "  Last used:")
        self.tokenfield = tokenfield(
            2, 15, 40, allow_inuse=True,
            keymap={keyboard.K_CLEAR: (self.dismiss, None)})
        self.description = ui.editfield(3, 15, 40)
        ui.map_fieldlist([self.tokenfield, self.description])
        self.user = ui.label(4, 15, 40)
        self.lastused = ui.label(5, 15, 40)
        self.opt_1 = ui.label(7, 2, 50)
        self.opt_2 = ui.label(8, 2, 50)
        self.tokenfield.sethook = self.tokenfield_set
        self.description.sethook = self.description_set
        self.tokenfield.focus()

    def tokenfield_set(self):
        t = self.tokenfield.f
        if t:
            dbt = td.s.query(UserToken).get(t)
            if dbt:
                self.description.set(dbt.description)
                self.user.set(dbt.user.fullname)
                self.lastused.set(dbt.last_seen)
                self.opt_1.set("1. Assign this token to a different user")
                self.opt_2.set("2. Forget about this token")
            else:
                self.description.set("")
                self.user.set("(not assigned)")
                self.lastused.set("")
                self.opt_1.set("1. Assign this token to a user")
                self.opt_2.set("")
        else:
            self.description.set("")
            self.user.set("")
            self.lastused.set("")
            self.opt_1.set("")
            self.opt_2.set("")

    def description_set(self):
        if self.tokenfield.f:
            dbt = td.s.query(UserToken).get(self.tokenfield.f)
            if dbt:
                dbt.description = self.description.f

    def keypress(self, k):
        if self.tokenfield.f:
            if k == "1":
                self.assign()
            elif k == "2":
                self.forget()

    def assign(self):
        dbt = td.s.query(UserToken).get(self.tokenfield.f)
        users = td.s.query(User)\
                    .filter(User.enabled == True)
        if dbt:
            users = users.filter(User.id != dbt.user_id)
        users = users.all()
        menu = [(user.fullname, self.finish_assign, (user.id,))
                for user in users]
        ui.menu(menu, title="Assign token to user", blurb="Choose the user "
                "to assign this token to")

    def forget(self):
        dbt = td.s.query(UserToken).get(self.tokenfield.f)
        if dbt:
            td.s.delete(dbt)
        self.tokenfield.set("")

    def finish_assign(self, userid):
        dbt = td.s.query(UserToken).get(self.tokenfield.f)
        if not dbt:
            dbt = UserToken(token=self.tokenfield.f,
                            description=self.description.f)
        user = td.s.query(User).get(userid)
        dbt.user = user
        td.s.add(dbt)
        self.dismiss()
        ui.infopopup(["Token {} ({}) assigned to {}.".format(
            dbt.token, dbt.description or "[no description]",
            user.fullname)],
                     title="Token assigned to user",
                     colour=ui.colour_confirm, dismiss=keyboard.K_CASH)

class adduser_cmd(cmdline.command):
    """Add a user.

    This user will be a superuser.  This is necessary during setup.
    """
    command = "adduser"
    help = "add a superuser to the database"

    @staticmethod
    def add_arguments(parser):
        parser.add_argument("fullname", help="Full name of user")
        parser.add_argument("shortname", help="Short name of user")
        parser.add_argument("usertoken", help="User ID token")

    @staticmethod
    def run(args):
        with td.orm_session():
            u = User(fullname=args.fullname, shortname=args.shortname,
                     enabled=True, superuser=True)
            t = UserToken(
                token=args.usertoken, user=u, description=args.fullname)
            td.s.add(u)
            td.s.add(t)
            print("User added.")

class listusers(cmdline.command):
    """List all active users.
    """
    help = "list active users"

    @staticmethod
    def run(args):
        with td.orm_session():
            users = td.s.query(User)\
                        .filter_by(enabled=True)\
                        .order_by(User.id)\
                        .all()
            for u in users:
                print("{:>4}: {}".format(u.id, u.fullname))

class default_groups:
    """Three basic group definitions.

    Pub configuration files can use these as they are, or add or
    remove individual items.
    """
    basic_user = set([
        "sell-stock",
        "sell-plu",
        "sell-dept",
        "take-payment",
        "cancel-line-in-open-transaction",
        "print-receipt",
        "recall-trans",
        "record-waste",
        "current-session-summary",
        "version",
        "netinfo",
        "kitchen-message",
        "kitchen-order",
        "edit-transaction-note",
        "price-check",
    ])

    skilled_user = set([
        "basic-user",
        "drink-in",
        "nosale",
        "merge-trans",
        "split-trans",
        "void-from-closed-transaction",
        "stock-check",
        "stock-level-check",
        "twitter",
        "use-stock",
        "restock",
        "auto-allocate",
        "manage-stockline-associations",
        "annotate",
    ])

    manager = set([
        "skilled-user",
        "print-receipt-by-number",
        "restore-deferred",
        "exit",
        "deliveries",
        "edit-supplier",
        "start-session",
        "end-session",
        "record-takings",
        "session-summary",
        "list-users",
        "edit-user",
        "manage-tokens",
        "override-price",
        "reprice-stock",
        "defer-trans",
        "edit-keycaps",
        "finish-unconnected-stock",
        "stock-history",
        "update-supplier",
        "purge-finished-stock",
        "alter-stocktype",
        "add-custom-transline",
        "reprint-stocklabel",
        "print-stocklist",
        "add-best-before",
        "create-stockline",
        "alter-stockline",
        "create-plu",
        "alter-plu",
        "alter-modifier",
        "return-finished-item",
        "recall-any-trans",
        "apply-discount",
    ])
