"""Widget builders for the managed Private cloud dashboard; the grid is 72 columns wide."""

INTEGER, STRING, HOST_GROUP, HOST, ITEM = 0, 1, 2, 3, 4
GREEN, YELLOW, RED, BLUE = "43A047", "FFB300", "E53935", "42A5F5"
PALETTE = ["1E88E5", "43A047", "FB8C00", "8E24AA", "E53935", "00ACC1", "6D4C41", "546E7A"]


class Items:
    """Item IDs by key for widgets that reference a single item."""

    def __init__(self, api, host_id):
        found = api.call("item.get", {"output": ["itemid", "key_"], "hostids": [host_id], "monitored": True})
        self.ids = {item["key_"]: item["itemid"] for item in found}

    def require(self, keys):
        missing = sorted(set(keys) - set(self.ids))
        if missing:
            raise RuntimeError("Dashboard items are missing: " + ", ".join(missing))

    def __getitem__(self, key):
        self.require([key])
        return self.ids[key]


def overview_page(config, items):
    pool = config["pool"]
    return page("Overview", [
        widget("problems", "Current problems", 0, 0, 36, 5, [field(HOST_GROUP, "groupids.0", config["group_id"]), field(INTEGER, "show_tags", 1), field(INTEGER, "show_opdata", 2)]),
        gauge("CPU utilization", 36, 0, items["system.cpu.util"], "100", (70, 90)),
        gauge("Memory utilization", 48, 0, items["vm.memory.util"], "100", (80, 90)),
        gauge("Pool " + pool + " capacity", 60, 0, items['zfs.pool.capacity["' + pool + '"]'], "100", (80, 90)),
        value("Uptime", 0, 5, items["system.uptime"]),
        value("Pool health", 12, 5, items['zfs.pool.health["' + pool + '"]']),
        value("ARC hit ratio", 24, 5, items["zfs.arc.hit_ratio"], 1),
        value("Uncorrected ECC errors", 36, 5, items["memory.ecc.errors.uncorrected"]),
        value("Encryption key loaded", 48, 5, items["zfs.secure.key_available"]),
        value("Snapshots", 60, 5, items["zfs.snapshots.total"]),
        graph("CPU", 0, 8, config["host"], ["CPU user time", "CPU system time", "CPU iowait time", "CPU softirq time"], stacked=True, maximum="100"),
        graph("Memory utilization", 36, 8, config["host"], ["Memory utilization"], maximum="100"),
        graph("Network " + config["interface"], 0, 14, config["host"], ["Interface " + config["interface"] + ": Bits received", "Interface " + config["interface"] + ": Bits sent"]),
        graph("Load average", 36, 14, config["host"], ["Load average (1m avg)", "Load average (5m avg)", "Load average (15m avg)"]),
    ])


def storage_page(config, items):
    pool = config["pool"]
    prefix = "Pool " + pool + ": "
    return page("Storage", [
        graph("Pool throughput", 0, 0, config["host"], [prefix + "Read throughput", prefix + "Write throughput"]),
        graph("Pool operations", 36, 0, config["host"], [prefix + "Read operations", prefix + "Write operations"]),
        honeycomb("Vdevs online", 0, 6, 36, 6, config["host_id"], ["Vdev *: Online"], r'Vdev .*/(.*): Online', [(0, RED), (1, GREEN)]),
        value("Allocated", 36, 6, items['zfs.pool.allocated["' + pool + '"]']),
        value("Free", 48, 6, items['zfs.pool.free["' + pool + '"]']),
        value("Fragmentation", 60, 6, items['zfs.pool.fragmentation["' + pool + '"]']),
        value("Last scrub age", 36, 9, items['zfs.pool.scrub.age["' + pool + '"]']),
        value("Last scrub errors", 48, 9, items['zfs.pool.scrub.errors["' + pool + '"]']),
        value("Checksum errors", 60, 9, items['zfs.pool.errors.checksum["' + pool + '"]']),
        graph("ARC size", 0, 12, config["host"], ["ZFS ARC: Size", "ZFS ARC: Target size"]),
        graph("ARC hit ratio", 36, 12, config["host"], ["ZFS ARC: Hit ratio"], maximum="100"),
    ])


def dataset_capacity_page(config, items):
    utilization = [
        field(HOST, "hostids.0", config["host_id"]), field(INTEGER, "layout", 1), field(INTEGER, "show_problems", 1),
        field(INTEGER, "item_ordering_order_by", 3), field(INTEGER, "item_ordering_order", 2), field(INTEGER, "item_ordering_limit", 7),
        field(INTEGER, "columns.0.display", 2), field(STRING, "columns.0.min", "0"), field(STRING, "columns.0.max", "100"),
        field(STRING, "columns.0.base_color", BLUE), field(INTEGER, "columns.0.decimal_places", 1),
        *thresholds("columns.0.thresholds", [(80, YELLOW), (90, RED)]),
    ]
    utilization += [field(STRING, "columns.0.items." + str(index), "Dataset " + name + ": Utilization") for index, name in enumerate(config["datasets"])]
    allocation = [field(INTEGER, "ds.0.dataset_type", 0), field(INTEGER, "draw_type", 0), field(INTEGER, "legend", 1), field(INTEGER, "legend_value", 1), field(INTEGER, "legend_lines_mode", 1), field(INTEGER, "legend_lines", 7)]
    for index, name in enumerate(config["datasets"]):
        allocation += [
            field(ITEM, "ds.0.itemids." + str(index), items['zfs.dataset.used["' + name + '"]']),
            field(STRING, "ds.0.color." + str(index), PALETTE[index % len(PALETTE)]),
            field(INTEGER, "ds.0.type." + str(index), 0),
        ]
    return page("Dataset capacity", [
        widget("topitems", "Leaf datasets by quota utilization", 0, 0, 36, 8, utilization),
        widget("piechart", "Current leaf dataset allocation", 36, 0, 36, 8, allocation),
    ])


def disks_page(config):
    return page("Disks", [
        honeycomb("Disk temperature", 0, 0, 36, 4, config["host_id"], ["*: Temperature"], r'\[(\S+) .*\]: Temperature', [(0, GREEN), (50, YELLOW), (60, RED)]),
        honeycomb("Power-on hours", 36, 0, 36, 4, config["host_id"], ["*: Power on hours"], r'\[(\S+) .*\]: Power on hours', [(0, BLUE)]),
        graph("Disk temperature", 0, 4, config["host"], ["*: Temperature"]),
        graph("Disk utilization", 36, 4, config["host"], ["*: Disk utilization"], maximum="100"),
        graph("Disk reads", 0, 10, config["host"], ["*: Disk read rate"]),
        graph("Disk writes", 36, 10, config["host"], ["*: Disk write rate"]),
    ])


def workloads_page(config, items):
    return page("Workloads", [
        top_items("Workloads by memory", 0, 0, config["host_id"], "Workload *: Memory"),
        top_items("Workloads by CPU cores", 36, 0, config["host_id"], "Workload *: CPU cores", 3),
        graph("Memory by workload", 0, 8, config["host"], ["Workload *: Memory"], stacked=True),
        graph("CPU cores by workload", 36, 8, config["host"], ["Workload *: CPU cores"], stacked=True),
        honeycomb("Container restarts", 0, 14, 72, 5, config["host_id"], ["Workload *: Restarts"], r'Workload [^/]*/(.*): Restarts', [(0, GREEN), (1, YELLOW)]),
        memory_share(0, 19, config["host"], items),
    ])


def memory_share(x, y, host, items):
    """Workload slices of total RAM; the unfilled part is memory used outside Kubernetes."""
    return widget("piechart", "Workload share of total memory", x, y, 72, 9, [
        field(INTEGER, "ds.0.dataset_type", 0),
        field(ITEM, "ds.0.itemids.0", items["vm.memory.size[total]"]), field(STRING, "ds.0.color.0", "B0BEC5"), field(INTEGER, "ds.0.type.0", 1),
        field(ITEM, "ds.0.itemids.1", items["vm.memory.size[available]"]), field(STRING, "ds.0.color.1", GREEN), field(INTEGER, "ds.0.type.1", 0),
        field(INTEGER, "ds.1.dataset_type", 1), field(STRING, "ds.1.hosts.0", host), field(STRING, "ds.1.items.0", "Workload *: Memory"), field(STRING, "ds.1.color", PALETTE[0]),
        field(INTEGER, "merge", 1), field(INTEGER, "merge_percent", 1), field(STRING, "merge_color", "78909C"),
        field(INTEGER, "legend", 1), field(INTEGER, "legend_value", 1), field(INTEGER, "legend_lines_mode", 1), field(INTEGER, "legend_lines", 10),
    ])


def services_page(config):
    widgets = [honeycomb("Certificate days left", 0, 0, 72, 5, config["host_id"], ["* certificate days"], r'(.*)-https certificate days', [(0, RED), (7, YELLOW), (21, GREEN)])]
    if config["alloy"]:
        widgets.append(graph("Alloy retries and drops", 0, 5, config["host"], ["alloy retries", "alloy dropped"]))
    return page("Services", widgets)


def page(name, widgets):
    return {"name": name, "display_period": 0, "widgets": widgets}


def widget(kind, name, x, y, width, height, fields):
    return {"type": kind, "name": name, "x": x, "y": y, "width": width, "height": height, "view_mode": 0, "fields": fields}


def field(kind, name, value):
    return {"type": kind, "name": name, "value": value}


def thresholds(prefix, levels):
    fields = []
    for index, (threshold, color) in enumerate(levels):
        fields += [field(STRING, prefix + "." + str(index) + ".color", color), field(STRING, prefix + "." + str(index) + ".threshold", str(threshold))]
    return fields


def gauge(name, x, y, item_id, maximum, levels):
    return widget("gauge", name, x, y, 12, 5, [
        field(ITEM, "itemid.0", item_id), field(STRING, "min", "0"), field(STRING, "max", maximum),
        field(INTEGER, "decimal_places", 0), field(INTEGER, "th_show_arc", 1),
        field(INTEGER, "show.0", 2), field(INTEGER, "show.1", 4), field(INTEGER, "show.2", 5),
        *thresholds("thresholds", [(0, GREEN), *((level, color) for level, color in zip(levels, (YELLOW, RED)))]),
    ])


def value(name, x, y, item_id, decimals=0):
    return widget("item", name, x, y, 12, 3, [field(ITEM, "itemid.0", item_id), field(INTEGER, "show.0", 2), field(INTEGER, "value_size", 20), field(INTEGER, "decimal_places", decimals)])


def top_items(name, x, y, host_id, pattern, decimals=2):
    return widget("topitems", name, x, y, 36, 8, [
        field(HOST, "hostids.0", host_id), field(INTEGER, "layout", 1),
        field(INTEGER, "item_ordering_order_by", 3), field(INTEGER, "item_ordering_order", 2), field(INTEGER, "item_ordering_limit", 10),
        field(STRING, "columns.0.items.0", pattern), field(INTEGER, "columns.0.decimal_places", decimals),
    ])


def honeycomb(name, x, y, width, height, host_id, patterns, label, levels):
    fields = [field(HOST, "hostids.0", host_id), field(STRING, "primary_label", "{{ITEM.NAME}.regsub(\"" + label + "\",\"\\1\")}"), field(INTEGER, "secondary_label_decimal_places", 0), *thresholds("thresholds", levels)]
    fields += [field(STRING, "items." + str(index), pattern) for index, pattern in enumerate(patterns)]
    return widget("honeycomb", name, x, y, width, height, fields)


def graph(name, x, y, host, patterns, stacked=False, maximum=None):
    """One data set per pattern keeps a distinct color for each series."""
    fields = [field(INTEGER, "legend_lines_mode", 1)]
    for index, pattern in enumerate(patterns):
        prefix = "ds." + str(index) + "."
        fields += [
            field(INTEGER, prefix + "dataset_type", 1), field(STRING, prefix + "hosts.0", host), field(STRING, prefix + "items.0", pattern),
            field(STRING, prefix + "color", PALETTE[index % len(PALETTE)]), field(INTEGER, prefix + "fill", 3 if stacked else 1),
            field(INTEGER, prefix + "stacked", 1 if stacked else 0),
        ]
    if maximum:
        fields += [field(STRING, "lefty_min", "0"), field(STRING, "lefty_max", maximum)]
    return widget("svggraph", name, x, y, 36, 6, fields)
