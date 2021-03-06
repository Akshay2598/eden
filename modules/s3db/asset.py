# -*- coding: utf-8 -*-

""" Sahana Eden Assets Model

    @copyright: 2009-2013 (c) Sahana Software Foundation
    @license: MIT

    Permission is hereby granted, free of charge, to any person
    obtaining a copy of this software and associated documentation
    files (the "Software"), to deal in the Software without
    restriction, including without limitation the rights to use,
    copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the
    Software is furnished to do so, subject to the following
    conditions:

    The above copyright notice and this permission notice shall be
    included in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
    OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
    HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
    WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
    OTHER DEALINGS IN THE SOFTWARE.
"""

__all__ = ["S3AssetModel",
           #"asset_rheader",
           "asset_types",
           "asset_log_status",
           "asset_controller",
           ]

try:
    import json # try stdlib (Python 2.6)
except ImportError:
    try:
        import simplejson as json # try external module
    except:
        import gluon.contrib.simplejson as json # fallback to pure-Python module

from gluon import *
from gluon.storage import Storage

from ..s3 import *
from s3layouts import S3AddResourceLink

ASSET_TYPE_VEHICLE   = 1   # => Extra Tab(s) for Registration Documents, Fuel Efficiency
ASSET_TYPE_RADIO     = 2   # => Extra Tab(s) for Radio Channels/Frequencies
ASSET_TYPE_TELEPHONE = 3   # => Extra Tab(s) for Contact Details & Airtime Billing
ASSET_TYPE_OTHER     = 4   # => No extra Tabs

# To pass to global scope
asset_types = {"VEHICLE"    : ASSET_TYPE_VEHICLE,
               "RADIO"      : ASSET_TYPE_RADIO,
               "TELEPHONE"  : ASSET_TYPE_TELEPHONE,
               "OTHER"      : ASSET_TYPE_OTHER,
               }

ASSET_LOG_SET_BASE = 1
ASSET_LOG_ASSIGN   = 2
ASSET_LOG_RETURN   = 3
ASSET_LOG_CHECK    = 4
ASSET_LOG_REPAIR   = 5
ASSET_LOG_DONATED  = 32
ASSET_LOG_LOST     = 33
ASSET_LOG_STOLEN   = 34
ASSET_LOG_DESTROY  = 35

# To pass to global scope
asset_log_status = {"SET_BASE" : ASSET_LOG_SET_BASE,
                    "ASSIGN"   : ASSET_LOG_ASSIGN,
                    "RETURN"   : ASSET_LOG_RETURN,
                    "CHECK"    : ASSET_LOG_CHECK,
                    "REPAIR"   : ASSET_LOG_REPAIR,
                    "DONATED"  : ASSET_LOG_DONATED,
                    "LOST"     : ASSET_LOG_LOST,
                    "STOLEN"   : ASSET_LOG_STOLEN,
                    "DESTROY"  : ASSET_LOG_DESTROY,
                    }

# =============================================================================
class S3AssetModel(S3Model):
    """
        Asset Management
    """

    names = ["asset_asset",
             "asset_item",
             "asset_log",
             "asset_asset_id",
             ]

    def model(self):

        T = current.T
        db = current.db
        auth = current.auth
        s3 = current.response.s3

        item_id = self.supply_item_id
        item_entity_id = self.supply_item_entity_id
        location_id = self.gis_location_id
        organisation_id = self.org_organisation_id
        person_id = self.pr_person_id

        messages = current.messages
        NONE = messages["NONE"]
        UNKNOWN_OPT = messages.UNKNOWN_OPT

        settings = current.deployment_settings
        org_site_label = settings.get_org_site_label()
        vehicle = settings.has_module("vehicle")

        # Shortcuts
        add_component = self.add_component
        configure = self.configure
        crud_strings = s3.crud_strings
        define_table = self.define_table
        super_link = self.super_link

        #--------------------------------------------------------------------------
        # Assets
        #
        asset_type_opts = {ASSET_TYPE_VEHICLE     : T("Vehicle"),
                           #ASSET_TYPE_RADIO      : T("Radio"),
                           #ASSET_TYPE_TELEPHONE  : T("Telephone"),
                           ASSET_TYPE_OTHER       : T("Other"),
                           }

        ctable = self.supply_item_category
        itable = self.supply_item
        supply_item_represent = self.supply_item_represent
        asset_items_set = db((ctable.can_be_asset == True) & \
                             (itable.item_category_id == ctable.id))

        tablename = "asset_asset"
        table = define_table(tablename,
                             # Instances
                             super_link("track_id", "sit_trackable"),
                             super_link("doc_id", "doc_entity"),
                             item_entity_id,
                             Field("number",
                                   label = T("Asset Number"),
                                   ),
                             # @ToDo: We could set this automatically based on Item Category
                             Field("type", "integer",
                                   label = T("Type"),
                                   readable = vehicle,
                                   writable = vehicle,
                                   requires = IS_IN_SET(asset_type_opts),
                                   default = ASSET_TYPE_OTHER,
                                   represent = lambda opt: \
                                       asset_type_opts.get(opt, UNKNOWN_OPT),
                                   ),
                             item_id(represent = supply_item_represent,
                                     requires = IS_ONE_OF(asset_items_set,
                                                          "supply_item.id",
                                                          supply_item_represent,
                                                          sort = True,
                                                          ),
                                     script = None, # No Item Pack Filter
                                     widget = None,
                                     ),
                             Field("kit", "boolean",
                                   default = False,
                                   label = T("Kit?"),
                                   represent = lambda bool: \
                                    (bool and [T("Yes")] or [NONE])[0],
                                   ),
                             organisation_id(#requires=self.org_organisation_requires(
                                             #           updateable=True,
                                             #           required=True),
                                             required = True,
                                             script = '''
S3OptionsFilter({
 'triggerName':'organisation_id',
 'targetName':'site_id',
 'lookupResource':'site',
 'lookupPrefix':'org',
 'lookupField':'site_id',
 'lookupURL':S3.Ap.concat('/org/sites_for_org/'),
})''',
                                             ),
                             # This is a component, so needs to be a super_link
                             # - can't override field name, ondelete or requires
                             super_link("site_id", "org_site",
                                        label = org_site_label,
                                        default = auth.user.site_id if auth.is_logged_in() else None,
                                        readable = True,
                                        writable = True,
                                        empty = False,
                                        ondelete = "RESTRICT",
                                        represent = self.org_site_represent,
                                        # Comment these to use a Dropdown & not an Autocomplete
                                        #widget = S3SiteAutocompleteWidget(),
                                        #comment = DIV(_class="tooltip",
                                        #              _title="%s|%s" % (T("Warehouse"),
                                        #                                T("Enter some characters to bring up a list of possible matches"))),
                                        ),
                             Field("sn",
                                   label = T("Serial Number"),
                                   ),
                             organisation_id("supply_org_id",
                                             label = T("Supplier/Donor"),
                                             ondelete = "SET NULL",
                                             ),
                             s3_date("purchase_date",
                                     label = T("Purchase Date"),
                                     ),
                             Field("purchase_price", "double",
                                   #default=0.00,
                                   represent=lambda v, row=None: \
                                    IS_FLOAT_AMOUNT.represent(v, precision=2),
                                   ),
                             s3_currency("purchase_currency"),
                             # Base Location, which should always be a Site & set via Log
                             location_id(readable=False,
                                         writable=False,
                                         ),
                             # Populated onaccept of the log to make a component tab
                             person_id("assigned_to_id",
                                       readable=False,
                                       writable=False,
                                       comment=self.pr_person_comment(child="assigned_to_id"),
                                       ),
                             s3_comments(),
                             *s3_meta_fields())

        # CRUD strings
        ADD_ASSET = T("Add Asset")
        crud_strings[tablename] = Storage(
            title_create = ADD_ASSET,
            title_display = T("Asset Details"),
            title_list =  T("Assets"),
            title_update = T("Edit Asset"),
            title_search = T("Search Assets"),
            title_upload = T("Import Assets"),
            subtitle_create = T("Add New Asset"),
            label_list_button =  T("List Assets"),
            label_create_button = ADD_ASSET,
            label_delete_button = T("Delete Asset"),
            msg_record_created = T("Asset added"),
            msg_record_modified = T("Asset updated"),
            msg_record_deleted = T("Asset deleted"),
            msg_list_empty = T("No Assets currently registered"))

        # Reusable Field
        asset_id = S3ReusableField("asset_id", table,
                                   sortby="number",
                                   requires = IS_NULL_OR(
                                                IS_ONE_OF(db, "asset_asset.id",
                                                          self.asset_represent,
                                                          sort=True)),
                                   represent = self.asset_represent,
                                   label = T("Asset"),
                                   comment = S3AddResourceLink(c="asset", f="asset",
                                    tooltip=T("If you don't see the asset in the list, you can add a new one by clicking link 'Add Asset'.")),
                                   ondelete = "CASCADE")

        # Which levels of Hierarchy are we using?
        hierarchy = current.gis.get_location_hierarchy()
        levels = hierarchy.keys()
        if len(settings.get_gis_countries()) == 1 or \
           s3.gis.config.region_location_id:
            levels.remove("L0")

        list_fields = ["id",
                       "item_id$item_category_id",
                       "item_id",
                       "number",
                       #"type",
                       #"purchase_date",
                       (T("Assigned To"), "assigned_to_id"),
                       "organisation_id",
                       "site_id",
                       ]

        report_fields = ["number",
                         (T("Category"), "item_id$item_category_id"),
                         (T("Item"), "item_id"),
                         "organisation_id",
                         "site_id",
                         ]

        text_fields = ["number",
                       "item_id$name",
                       #"item_id$category_id$name",
                       "comments",
                       ]

        for level in levels:
            lfield = "location_id$%s" % level
            report_fields.append(lfield)
            text_fields.append(lfield)
            list_fields.append(lfield)

        list_fields.append("comments")

        filter_widgets = [
            S3TextFilter(text_fields,
                         label = T("Search"),
                         comment = T("You can search by asset number, item description or comments. You may use % as wildcard. Press 'Search' without input to list all assets."),
                         #_class = "filter-search",
                         ),
            S3OptionsFilter("item_id$item_category_id",
                            # @ToDo: Introspect need for header based on # records
                            #header = True,
                            #label = T("Category"),
                            represent = "%(name)s",
                            widget = "multiselect",
                            ),
            S3OptionsFilter("organisation_id",
                            # @ToDo: Introspect need for header based on # records
                            #header = True,
                            #label = T("Organization"),
                            represent = "%(name)s",
                            widget = "multiselect",
                            ),
            S3LocationFilter("location_id",
                             #hidden = True,
                             #label = T("Location"),
                             levels = levels,
                             widget = "multiselect",
                             ),
            ]

        report_options = Storage(
            rows = report_fields,
            cols = report_fields,
            fact = [(T("Number of items"), "count(number)")],
            defaults=Storage(cols = "location_id$%s" % levels[0], # Highest-level of hierarchy
                             fact = "count(number)",
                             rows = "item_id$item_category_id",
                             totals = True,
                             )
            )

        # Custom CRUD Form to allow ad-hoc Kits
        crud_form = S3SQLCustomForm("number",
                                    "type",
                                    "item_id",
                                    "organisation_id",
                                    "site_id",
                                    "kit",
                                    # If not ad-hoc Kit
                                    "sn",
                                    "supply_org_id",
                                    "purchase_date",
                                    "purchase_price",
                                    "purchase_currency",
                                    # If ad-hoc Kit
                                    S3SQLInlineComponent(
                                        "item",
                                        label = T("Items"),
                                        fields = ["item_id",
                                                  "quantity",
                                                  "sn",
                                                  # These are too wide for the screen & hence hide the AddResourceLinks
                                                  #"supply_org_id",
                                                  #"purchase_date",
                                                  #"purchase_price",
                                                  #"purchase_currency",
                                                  "comments",
                                                  ],
                                        ),
                                    "comments",
                                    )

        # Resource Configuration
        configure(tablename,
                  # Open Tabs after creation
                  create_next = URL(c="asset", f="asset",
                                    args=["[id]"]),
                  crud_form = crud_form,
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  mark_required = ["organisation_id"],
                  onaccept = self.asset_onaccept,
                  realm_components = ["log", "presence"],
                  report_options = report_options,
                  super_entity = ("supply_item_entity", "sit_trackable"),
                  update_realm = True,
                  )

        # Log as component of Assets
        add_component("asset_log", asset_asset="asset_id")

        # Vehicles as component of Assets
        add_component("vehicle_vehicle",
                      asset_asset=dict(joinby="asset_id",
                                       multiple=False))

        # GPS as a component of Assets
        add_component("vehicle_gps", asset_asset="asset_id")

        # Asset Items
        add_component("asset_item",
                      asset_asset="asset_id")

        # =====================================================================
        # Asset Items
        # - to allow building ad-hoc Kits
        #
        tablename = "asset_item"
        table = define_table(tablename,
                             item_entity_id,
                             asset_id(ondelete="CASCADE"),
                             item_id(represent = supply_item_represent,
                                     requires = IS_ONE_OF(asset_items_set,
                                                          "supply_item.id",
                                                          supply_item_represent,
                                                          sort = True,
                                                          ),
                                     script = None, # No Item Pack Filter
                                     widget = None,
                                     ),
                             Field("quantity", "integer", notnull=True,
                                   default = 1,
                                   label = T("Quantity"),
                                   requires = IS_INT_IN_RANGE(1, 1000),
                                   ),
                             Field("sn",
                                   label = T("Serial Number")),
                             organisation_id("supply_org_id",
                                             label = T("Supplier/Donor"),
                                             ondelete = "SET NULL"),
                             s3_date("purchase_date",
                                     label = T("Purchase Date")),
                             Field("purchase_price", "double",
                                   #default=0.00,
                                   represent=lambda v, row=None: \
                                    IS_FLOAT_AMOUNT.represent(v, precision=2)),
                             s3_currency("purchase_currency"),
                             # Base Location, which should always be a Site & set via Log
                             location_id(readable=False,
                                         writable=False),
                             s3_comments(comment=None),
                             *s3_meta_fields())

        # =====================================================================
        # Asset Log
        #
        asset_log_status_opts = {ASSET_LOG_SET_BASE : T("Base %(facility)s Set") % dict(facility = org_site_label),
                                 ASSET_LOG_ASSIGN   : T("Assigned"),
                                 ASSET_LOG_RETURN   : T("Returned"),
                                 ASSET_LOG_CHECK    : T("Checked"),
                                 ASSET_LOG_REPAIR   : T("Repaired"),
                                 ASSET_LOG_DONATED  : T("Donated"),
                                 ASSET_LOG_LOST     : T("Lost"),
                                 ASSET_LOG_STOLEN   : T("Stolen"),
                                 ASSET_LOG_DESTROY  : T("Destroyed"),
                                 }

        asset_condition_opts = {1:T("Good Condition"),
                                2:T("Minor Damage"),
                                3:T("Major Damage"),
                                4:T("Un-Repairable"),
                                5:T("Needs Maintenance"),
                                }

        if auth.permission.format == "html":
            # T isn't JSON serializable
            site_types = auth.org_site_types
            for key in site_types.keys():
                site_types[key] = str(site_types[key])
            site_types = json.dumps(site_types)
            script = '''
S3OptionsFilter({
 'triggerName':'organisation_id',
 'targetName':'site_id',
 'lookupPrefix':'org',
 'lookupResource':'site',
 'lookupField':'site_id',
 'fncRepresent': function(record,PrepResult){
  var InstanceTypeNice=%(instance_type_nice)s
  return record.name+" ("+InstanceTypeNice[record.instance_type]+")"
}})''' % dict(instance_type_nice = site_types)
        else:
            script = None

        tablename = "asset_log"
        table = define_table(tablename,
                             asset_id(),
                             Field("status", "integer",
                                   label = T("Status"),
                                   requires = IS_IN_SET(asset_log_status_opts),
                                   represent = lambda opt: \
                                       asset_log_status_opts.get(opt, UNKNOWN_OPT)
                                   ),
                             s3_datetime("datetime",
                                         default="now",
                                         empty=False,
                                         represent="date",
                                         ),
                             s3_datetime("datetime_until",
                                         label = T("Date Until"),
                                         represent="date",
                                         ),
                             person_id(label = T("Assigned To")),
                             Field("check_in_to_person", "boolean",
                                   #label = T("Mobile"),      # Relabel?
                                   label = T("Track with this Person?"),
                                   
                                   comment = DIV(_class="tooltip",
                                                 #_title="%s|%s" % (T("Mobile"),
                                                 _title="%s|%s" % (T("Track with this Person?"),
                                                                   T("If selected, then this Asset's Location will be updated whenever the Person's Location is updated."))),
                                   readable = False,
                                   writable = False),
                             # The Organisation to whom the loan is made
                             organisation_id(
                                    readable = False,
                                    writable = False,
                                    widget = None
                                    ),
                             # This is a component, so needs to be a super_link
                             # - can't override field name, ondelete or requires
                             super_link("site_id", "org_site",
                                        label = org_site_label,
                                        #filterby = "site_id",
                                        #filter_opts = auth.permitted_facilities(redirect_on_error=False),
                                        instance_types = auth.org_site_types,
                                        updateable = True,
                                        not_filterby = "obsolete",
                                        not_filter_opts = [True],
                                        #default = user.site_id if is_logged_in() else None,
                                        readable = True,
                                        writable = True,
                                        empty = False,
                                        represent = self.org_site_represent,
                                        #widget = S3SiteAutocompleteWidget(),
                                        script = script,
                                        ),
                             self.org_room_id(),
                             #location_id(),
                             Field("cancel", "boolean",
                                   default = False,
                                   label = T("Cancel Log Entry"),
                                   represent = s3_yes_no_represent,
                                   comment = DIV(_class="tooltip",
                                                 _title="%s|%s" % (T("Cancel Log Entry"),
                                                                   T("'Cancel' will indicate an asset log entry did not occur")))
                                   ),
                             Field("cond", "integer",  # condition is a MySQL reserved word
                                   requires = IS_IN_SET(asset_condition_opts,
                                                        zero = "%s..." % T("Please select")),
                                   represent = lambda opt: \
                                       asset_condition_opts.get(opt, UNKNOWN_OPT),
                                   label = T("Condition")),
                             person_id("by_person_id",
                                       label = T("Assigned By"),               # This can either be the Asset controller if signed-out from the store
                                       default = auth.s3_logged_in_person(),   # or the previous owner if passed on directly (e.g. to successor in their post)
                                       comment = self.pr_person_comment(child="by_person_id"),
                                       ),
                             s3_comments(),
                             *s3_meta_fields())

        # CRUD strings
        ADD_ASSIGN = T("New Entry in Asset Log")
        crud_strings[tablename] = Storage(
            title_create = ADD_ASSIGN,
            title_display = T("Asset Log Details"),
            title_list = T("Asset Log"),
            title_update = T("Edit Asset Log Entry"),
            title_search = T("Search Asset Log"),
            subtitle_create = ADD_ASSIGN,
            label_list_button = T("Asset Log"),
            label_create_button = ADD_ASSIGN,
            label_delete_button = T("Delete Asset Log Entry"),
            msg_record_created = T("Entry added to Asset Log"),
            msg_record_modified = T("Asset Log Entry updated"),
            msg_record_deleted = T("Asset Log Entry deleted"),
            msg_list_empty = T("Asset Log Empty"))

        # Resource configuration
        configure(tablename,
                  listadd = False,
                  list_fields = ["id",
                                 "datetime",
                                 "status",
                                 "datetime_until",
                                 "organisation_id",
                                 "site_id",
                                 "room_id",
                                 #"location_id",
                                 "cancel",
                                 "cond",
                                 "comments",
                                 ],
                  onaccept = self.asset_log_onaccept,
                  )

        # ---------------------------------------------------------------------
        # Pass names back to global scope (s3.*)
        #
        return dict(asset_asset_id = asset_id,
                    asset_represent = self.asset_represent,
                    )

    # -------------------------------------------------------------------------
    @staticmethod
    def defaults():
        """ Return safe defaults for names in case the model is disabled """

        asset_id = S3ReusableField("asset_id", "integer",
                                   writable=False,
                                   readable=False)
        return Storage(asset_asset_id=asset_id)

    # -------------------------------------------------------------------------
    @staticmethod
    def asset_represent(id, row=None):
        """
            Represent an Asset
        """

        if row:
            id = row.id
        elif not id:
            return current.messages["NONE"]

        db = current.db
        table = db.asset_asset
        itable = db.supply_item
        btable = db.supply_brand
        query = (table.id == id) & \
                (itable.id == table.item_id)
        r = db(query).select(table.number,
                             itable.name,
                             btable.name,
                             left = btable.on(itable.brand_id == btable.id),
                             limitby=(0, 1)).first()
        try:
            represent = "%s (%s" % (r.asset_asset.number,
                                    r.supply_item.name)
            if r.supply_brand.name:
                represent = "%s, %s)" % (represent,
                                         r.supply_brand.name)
            else:
                represent = "%s)" % represent
        except:
            represent = current.messages.UNKNOWN_OPT
        return represent

    # -------------------------------------------------------------------------
    @staticmethod
    def asset_onaccept(form):
        """
            After DB I/O
        """

        form_vars = form.vars
        kit = form_vars.get("kit", None)
        site_id = form_vars.get("site_id", None)
        if site_id:
            db = current.db
            atable = db.asset_asset
            stable = db.org_site
            asset_id = form_vars.id
            # Set the Base Location
            tracker = S3Tracker()
            asset_tracker = tracker(atable, asset_id)
            location_id = asset_tracker.set_base_location(tracker(stable, site_id))
            if kit:
                # Also populate location_id field in component items
                aitable = db.asset_item
                db(aitable.asset_id == asset_id).update(location_id = location_id)
            # Add a log entry for this
            ltable = db.asset_log
            ltable.insert(asset_id = asset_id,
                          status = ASSET_LOG_SET_BASE,
                          organisation_id = form_vars.get("organisation_id", None),
                          site_id = site_id,
                          cond = 1,
                          )

        if kit:
            # Empty any inappropriate fields
            db(atable.id == asset_id).update(supplier_org_id = None,
                                             purchase_date = None,
                                             purchase_price = None,
                                             purchase_currency = None,
                                             )
        else:
            # Delete any component items
            aitable = db.asset_item
            ids = db(aitable.asset_id == asset_id).select(aitable.id).as_list()
            if ids:
                resource = current.s3db.resource("asset_item", ids)
                resource.delete()

        return

    # -------------------------------------------------------------------------
    @staticmethod
    def asset_log_onaccept(form):
        """
            After DB I/O
        """

        request = current.request
        status = request.vars.pop("status", None)
        if not status:
            # e.g. Import or Record merger
            return

        form_vars = form.vars
        status = int(form_vars.status or status)

        db = current.db
        ltable = db.asset_log
        row = db(ltable.id == form_vars.id).select(ltable.asset_id,
                                                   limitby=(0, 1)
                                                   ).first()
        try:
            asset_id = row.asset_id
        except:
            return

        current_log = asset_get_current_log(asset_id)

        type = request.get_vars.pop("type", None)
        log_time = current_log.datetime
        current_time = form_vars.get("datetime", None).replace(tzinfo=None)
        if log_time <= current_time:
            # This is a current assignment
            atable = db.asset_asset
            aitable = db.asset_item
            tracker = S3Tracker()
            asset_tracker = tracker(atable, asset_id)

            if status == ASSET_LOG_SET_BASE:
                # Set Base Location
                location_id = asset_tracker.set_base_location(tracker(db.org_site,
                                                                      form_vars.site_id))
                # Also do component items
                db(aitable.asset_id == asset_id).update(location_id = location_id)

            elif status == ASSET_LOG_ASSIGN:
                if type == "person":#
                    if form_vars.check_in_to_person:
                        asset_tracker.check_in(db.pr_person, form_vars.person_id,
                                               timestmp = request.utcnow)
                        # Also do component items
                        # @ToDo: Have these move when the person moves
                        locations = asset_tracker.get_location(_fields=[db.gis_location.id])
                        try:
                            db(aitable.asset_id == asset_id).update(location_id = locations[0].id)
                        except:
                            pass
                    else:
                        location_id = asset_tracker.set_location(form_vars.person_id,
                                                                 timestmp = request.utcnow)
                        # Also do component items
                        db(aitable.asset_id == asset_id).update(location_id = location_id)
                    # Update main record for component
                    db(atable.id == asset_id).update(assigned_to_id=form_vars.person_id)

                elif type == "site":
                    asset_tracker.check_in(db.org_site, form_vars.site_id,
                                           timestmp = request.utcnow)
                    # Also do component items
                    locations = asset_tracker.get_location(_fields=[db.gis_location.id])
                    try:
                        db(aitable.asset_id == asset_id).update(location_id = locations[0].id)
                    except:
                        pass

                elif type == "organisation":
                    if form_vars.site_id:
                        asset_tracker.check_in(db.org_site, form_vars.site_id,
                                               timestmp = request.utcnow)
                        # Also do component items
                        locations = asset_tracker.get_location(_fields=[db.gis_location.id])
                        try:
                            db(aitable.asset_id == asset_id).update(location_id = locations[0].id)
                        except:
                            pass
                    else:
                        # We can no longer track location
                        asset_tracker.check_out()

            elif status == ASSET_LOG_RETURN:
                # Set location to base location
                location_id = asset_tracker.set_location(asset_tracker,
                                                         timestmp = request.utcnow)
                # Also do component items
                db(aitable.asset_id == asset_id).update(location_id = location_id)

        return

# =============================================================================
def asset_get_current_log(asset_id):
    """
        Get the current log entry for this asset
    """

    table = current.s3db.asset_log
    query = (table.asset_id == asset_id) & \
            (table.cancel == False) & \
            (table.deleted == False)
    # Get the log with the maximum time
    asset_log = current.db(query).select(table.id,
                                         table.status,
                                         table.datetime,
                                         table.cond,
                                         table.person_id,
                                         table.organisation_id,
                                         table.site_id,
                                         #table.location_id,
                                         orderby = ~table.datetime,
                                         limitby=(0, 1)).first()
    if asset_log:
        return Storage(datetime = asset_log.datetime,
                       person_id = asset_log.person_id,
                       cond = int(asset_log.cond or 0),
                       status = int(asset_log.status or 0),
                       organisation_id = asset_log.organisation_id,
                       site_id = asset_log.site_id,
                       #location_id = asset_log.location_id
                       )
    else:
        return Storage()

# =============================================================================
def asset_log_prep(r):
    """
        Called by Controller
    """

    T = current.T
    db = current.db
    request = current.request

    table = db.asset_log

    if r.record:
        asset = Storage(r.record)
    else:
        # This is a new record
        asset = Storage()
        table.cancel.readable = False
        table.cancel.writable = False

    # This causes an error with the dataTables paginate
    # if used only in r.interactive & not also r.representation=="aadata"
    if r.method != "read" and r.method != "update":
        table.cancel.readable = False
        table.cancel.writable = False
    current_log = asset_get_current_log(asset.id)
    if request.vars.status:
        status = int(request.vars.status)
    else:
        status = 0

    if status and status != "None":
        field = table.status
        field.default = status
        field.readable = False
        field.writable = False
    elif current_log:
        table.status.default = current_log.status

    if current_log.organisation_id:
        table.organisation_id.default = current_log.organisation_id
        table.site_id.requires = IS_ONE_OF(db, "org_site.site_id",
                                           table.site_id.represent,
                                           filterby = "organisation_id",
                                           filter_opts = [current_log.organisation_id])

    crud_strings = current.response.s3.crud_strings.asset_log
    if status == ASSET_LOG_SET_BASE:
        crud_strings.subtitle_create = T("Set Base Facility/Site")
        crud_strings.msg_record_created = T("Base Facility/Site Set")
        table.by_person_id.label = T("Set By")
        table.site_id.writable = True
        table.datetime_until.readable = False
        table.datetime_until.writable = False
        table.person_id.readable = False
        table.person_id.writable = False
        table.organisation_id.readable = True
        table.organisation_id.writable = True
        table.site_id.requires = IS_ONE_OF(db, "org_site.site_id",
                                           table.site_id.represent)

    elif status == ASSET_LOG_RETURN:
        crud_strings.subtitle_create = T("Return")
        crud_strings.msg_record_created = T("Returned")
        table.person_id.label = T("Returned From")
        table.person_id.default = current_log.person_id
        table.site_id.readable = False
        table.site_id.writable = False

    elif status == ASSET_LOG_ASSIGN:
        type = request.vars.type
        # table["%s_id" % type].required = True
        if type == "person":
            crud_strings.subtitle_create = T("Assign to Person")
            crud_strings.msg_record_created = T("Assigned to Person")
            table["person_id"].requires = IS_ONE_OF(db, "pr_person.id",
                                                    table.person_id.represent,
                                                    orderby="pr_person.first_name",
                                                    sort=True,
                                                    error_message="Person must be specified!")
            table.check_in_to_person.readable = True
            table.check_in_to_person.writable = True
            table.site_id.requires = IS_NULL_OR(
                                        IS_ONE_OF(db, "org_site.site_id",
                                                  table.site_id.represent))
        elif type == "site":
            crud_strings.subtitle_create = T("Assign to Facility/Site")
            crud_strings.msg_record_created = T("Assigned to Facility/Site")
        elif type == "organisation":
            crud_strings.subtitle_create = T("Assign to Organization")
            crud_strings.msg_record_created = T("Assigned to Organization")
            table.organisation_id.readable = True
            table.organisation_id.writable = True
            table.organisation_id.requires = IS_ONE_OF(db, "org_organisation.id",
                                                       table.organisation_id.represent,
                                                       orderby="org_organisation.name",
                                                       sort=True)
            table.site_id.requires = IS_NULL_OR(
                                        IS_ONE_OF(db, "org_site.site_id",
                                                  table.site_id.represent))
    elif "status" in request.get_vars:
        crud_strings.subtitle_create = T("Update Status")
        crud_strings.msg_record_created = T("Status Updated")
        table.person_id.label = T("Updated By")
        field = table.status
        field.readable = True
        field.writable = True
        field.requires = IS_IN_SET({ASSET_LOG_CHECK    : T("Check"),
                                    ASSET_LOG_REPAIR   : T("Repair"),
                                    ASSET_LOG_DONATED  : T("Donated"),
                                    ASSET_LOG_LOST     : T("Lost"),
                                    ASSET_LOG_STOLEN   : T("Stolen"),
                                    ASSET_LOG_DESTROY  : T("Destroyed"),
                                    })

# =============================================================================
def asset_rheader(r):
    """ Resource Header for Assets """

    if r.representation == "html":
        record = r.record
        if record:

            T = current.T
            s3db = current.s3db
            s3 = current.response.s3

            NONE = current.messages["NONE"]

            if record.type == ASSET_TYPE_VEHICLE:
                tabs = [(T("Asset Details"), None, {"native": True}),
                        (T("Vehicle Details"), "vehicle"),
                        (T("GPS Data"), "gps")]
            else:
                tabs = [(T("Edit Details"), None)]
            #elif record.type == s3.asset.ASSET_TYPE_RADIO:
            #    tabs.append((T("Radio Details"), "radio"))
            #elif record.type == s3.asset.ASSET_TYPE_TELEPHONE:
            #    tabs.append((T("Telephone Details"), "phone"))
            tabs.append((T("Log"), "log"))
            tabs.append((T("Documents"), "document"))

            rheader_tabs = s3_rheader_tabs(r, tabs)


            if current.request.controller == "vehicle":
                func = "vehicle"
            else:
                func = "asset"

            # @ToDo: Check permissions before displaying buttons

            asset_action_btns = [
                A(T("Set Base Facility/Site"),
                  _href = URL(f=func,
                              args = [record.id, "log", "create"],
                              vars = dict(status = ASSET_LOG_SET_BASE)
                              ),
                  _class = "action-btn",
                  )
                ]

            current_log = asset_get_current_log(record.id)
            status = current_log.status

            #if record.location_id:
            # A Base Site has been set
            # Return functionality removed  - as it doesn't set site_id & organisation_id in the logs
            #if status == ASSET_LOG_ASSIGN:
            #    asset_action_btns += [ A( T("Return"),
            #                              _href = URL(f=func,
            #                                          args = [record.id, "log", "create"],
            #                                          vars = dict(status = ASSET_LOG_RETURN)
            #                                        ),
            #                              _class = "action-btn"
            #                            )
            #                           ]
            if status < ASSET_LOG_DONATED:
                # @ToDo: deployment setting to prevent assigning assets before returning them
                # The Asset is available for assignment (not disposed)
                asset_action_btns += [
                    A(T("Assign to Person"),
                      _href = URL(f=func,
                                  args = [record.id, "log", "create"],
                                  vars = dict(status = ASSET_LOG_ASSIGN,
                                              type = "person")
                                  ),
                      _class = "action-btn",
                      ),
                    A(T("Assign to Facility/Site"),
                      _href = URL(f=func,
                                  args = [record.id, "log", "create"],
                                  vars = dict(status = ASSET_LOG_ASSIGN,
                                              type = "site")
                                  ),
                      _class = "action-btn",
                    ),
                    A(T("Assign to Organization"),
                      _href = URL(f=func,
                                  args = [record.id, "log", "create"],
                                  vars = dict(status = ASSET_LOG_ASSIGN,
                                              type = "organisation")
                                  ),
                      _class = "action-btn",
                      ),
                    ]
            asset_action_btns += [
                A(T("Update Status"),
                  _href = URL(f=func,
                              args = [record.id, "log", "create"],
                              vars = None
                              ),
                  _class = "action-btn",
                  ),
                ]

            table = r.table
            ltable = s3db.asset_log
            rheader = DIV(TABLE(TR(TH("%s: " % table.number.label),
                                   record.number,
                                   TH("%s: " % table.item_id.label),
                                   table.item_id.represent(record.item_id)
                                   ),
                                TR(TH("%s: " % ltable.cond.label),
                                   ltable.cond.represent(current_log.cond),
                                   TH("%s: " % ltable.status.label),
                                   ltable.status.represent(status),
                                   ),
                                TR(TH("%s: " % ltable.person_id.label),
                                   ltable.person_id.represent(current_log.person_id),
                                   TH("%s: " % ltable.site_id.label),
                                   ltable.site_id.represent(current_log.site_id),
                                   ),
                                ),
                          DIV(_style = "margin-top:5px;", # @ToDo: Move to CSS
                              *asset_action_btns
                              ),
                          rheader_tabs)
            return rheader
    return None

# =============================================================================
def asset_controller():
    """ RESTful CRUD controller """

    s3 = current.response.s3

    # Pre-process
    def prep(r):
        # Location Filter
        current.s3db.gis_location_filter(r)

        if r.component_name == "log":
            asset_log_prep(r)

        return True
    s3.prep = prep

    # Post-processor
    def postp(r, output):
        if r.interactive and r.method != "import":
            script = "/%s/static/scripts/S3/s3.asset.js" % r.application
            s3.scripts.append(script)
            S3CRUD.action_buttons(r, deletable=False)
            #if not r.component:
                #s3.actions.append({"url" : URL(c="asset", f="asset",
                #                               args = ["[id]", "log", "create"],
                #                               vars = {"status" : eden.asset.asset_log_status["ASSIGN"],
                #                                       "type" : "person"}),
                #                   "_class" : "action-btn",
                #                   "label" : str(T("Assign"))})
        return output
    s3.postp = postp

    output = current.rest_controller("asset", "asset",
                                     hide_filter = False,
                                     rheader = asset_rheader,
                                     )
    return output

# END =========================================================================
