import re
import socket
from uuid import uuid1

from stix2 import File, Bundle, Process, IPv4Address, IPv6Address, DomainName, Grouping, MalwareAnalysis

from cuckoo.common.abstracts import Report


class ObservableObject:
    def __init__(self, name, containerid, command, timestamp):
        self.name = name
        self.containerid = containerid
        self.command = command
        self.timestamp = timestamp

    def __lt__(self, other):
        if self.name < other.name:
            return True
        return False

    def __eq__(self, other):
        if isinstance(other, list):
            return False
        if self.name != other.name or self.containerid != other.containerid:
            return False
        return True

    def __hash__(self):
        return hash(str(self))


class Stix2(Report):
    CWD = ""

    def init(self):
        self.classifiers = [
            {
                "name": "files_removed",
                "key_word": ["unlink", "unlinkat", "rmdir"],
                "regexes": [
                    r"unlink\(\"(.*?)\"",
                    r"unlinkat\(.*?\"(.*?)\"",
                    r"rmdir\(\"(.*?)\"",
                ],
                "prepare": lambda ob: ob if ob.startswith("/") else self.CWD + "/" + str(ob),
            },
            {
                "name": "files_read",
                "key_word": ["openat"],
                "regexes": [r"openat\(.*?\"(?P<filename>.*?)\".*?(?:O_RDWR|O_RDONLY).*?\)"],
                "prepare": lambda ob: ob if ob.startswith("/") else self.CWD + "/" + str(ob),
            },
            {
                "name": "files_written",
                "key_word": ["openat", "rename", "link", "mkdir"],
                "regexes": [
                    r"openat\(.*?\"(.*?)\".*?(?:O_RDWR|O_WRONLY|O_CREAT|O_APPEND)",
                    r"(?:link|rename)\(\".*?\", \"(.*?)\"\)",
                    r"mkdir\(\"(.*?)\"",
                ],
                "prepare": lambda ob: ob if ob.startswith("/") else self.CWD + "/" + str(ob),
            },
            {
                "name": "hosts_connected",
                "key_word": ["connect"],
                "regexes": [r"connect\(.*?{AF_INET(?:6) i?, (.*?), (.*?)},"],
                "prepare": lambda ob: str(ob[0]) + ":" + str(ob[1]),
            },
            {
                "name": "processes_created",
                "key_word": ["execve"],
                "regexes": [r"execve\(.*?\[(.*?)\]"],
                "prepare": lambda ob: ob.replace('"', "").replace(",", ""),
            },
            {
                "name": "domains",
                "key_word": ["connect"],
                "regexes": [r"connect\(.*?{AF_INET(?:6)?, (.*?),"],
                "prepare": lambda ob: Stix2.ip2domain(ob),
            },
        ]

        self.key_words = [key_word for classifier in self.classifiers for key_word in classifier["key_word"]]

    @staticmethod
    def ip2domain(ip):
        try:
            return socket.gethostbyaddr(ip)[0]
        except BaseException as e:
            return ip

    def line_is_relevant(self, line):
        for word in self.key_words:
            if word in line:
                return True

    @staticmethod
    def get_containerid(observable):
        regex = r"([0-9a-z]*)[|]"
        if re.search(regex, observable):
            return re.search(regex, observable).group(1)
        return ""

    @staticmethod
    def is_on_whitelist(line):
        whitelist = [
            '/root/.npm/_cacache',  # npm cache
            '/root/.npm/_locks',  # npm locks
            '/root/.npm/anonymous-cli-metrics.json',  # npm metrics
            '/root/.npm/_logs',  # npm logs
        ]

        return any([line.startswith(_) for _ in whitelist])

    @staticmethod
    def parse_observables_to_files(key, observables):
        list_of_stix_files = [
            File(
                type="file",
                id="file--" + str(uuid1()),
                name=stix_file.name,
                custom_properties={
                    "container_id": stix_file.containerid,
                    "timestamp": stix_file.timestamp,
                    "full_output": stix_file.command,
                },
                allow_custom=True,
            )
            for stix_file in observables
        ]
        return Grouping(
            type="grouping",
            name=key,
            context="suspicious-activity",
            object_refs=list_of_stix_files,
        ), list_of_stix_files

    @staticmethod
    def parse_hosts_to_ip_mac_addresses(key, observables):
        ip_regex = r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}"
        list_of_stix_hosts = []
        for host in observables:
            if re.search(ip_regex, host.command):
                stix_ip = IPv4Address(
                    type="ipv4-addr",
                    value=host.name,
                    custom_properties={
                        "container_id": host.containerid,
                        "timestamp": host.timestamp,
                        "full_output": host.command,
                    },
                    allow_custom=True,
                )
            else:
                stix_ip = IPv6Address(
                    type="ipv6-addr",
                    value=host.name,
                    custom_properties={
                        "container_id": host.containerid,
                        "timestamp": host.timestamp,
                        "full_output": host.command
                    },
                    allow_custom=True,
                )
            list_of_stix_hosts.append(stix_ip)
        return Grouping(
            type="grouping",
            name=key,
            context="suspicious-activity",
            object_refs=list_of_stix_hosts,
        ), list_of_stix_hosts

    @staticmethod
    def is_known_process(known_processes, process):
        for known in known_processes:
            if process.name == known.command_line:
                return True
        return False

    @staticmethod
    def parse_observables_to_processes(key, observables):
        list_of_stix_processes = []
        for process in observables:
            if not Stix2.is_known_process(list_of_stix_processes, process):
                list_of_stix_processes.append(Process(
                    type="process",
                    command_line=process.name,
                    custom_properties={
                        "container_id": process.containerid,
                        "timestamp": process.timestamp,
                        "full_output": process.command,
                        "executable_path": Stix2.get_executable_path(process)
                    },
                    allow_custom=True,
                ))
        return Grouping(
            type="grouping",
            name=key,
            context="suspicious-activity",
            object_refs=list_of_stix_processes,
        ), list_of_stix_processes

    @staticmethod
    def get_executable_path(process):
        regex_for_executable_name = r"execve\(\"([^\"]*)\""
        search_result = re.search(regex_for_executable_name, process.command)
        if not search_result:
            return ""
        return search_result.group(1)

    @staticmethod
    def parse_observables_to_domains(key, observables):
        list_of_stix_domains = [
            DomainName(
                type="domain-name",
                value=domain.name,
                custom_properties={
                    "container_id": domain.containerid,
                    "timestamp": domain.timestamp,
                    "full_output": domain.command,
                },
                allow_custom=True,
            )
            for domain in observables
        ]
        return Grouping(
            type="grouping",
            name=key,
            context="suspicious-activity",
            object_refs=list_of_stix_domains,
        ), list_of_stix_domains

    def run(self, results):
        self.init()

        syscalls = open(self.analysis_path + "/logs/all.stap", "r").read()

        find_execution_of_build_script = re.findall(r"execve\(.*?\"-c\", \"(.*?)\/[^\"\/]+\"", syscalls)
        self.CWD = find_execution_of_build_script[0]

        final = {}
        stix = {}
        for classifier in self.classifiers:
            final[classifier['name']] = set()
            stix[classifier['name']] = set()

        for line in syscalls.splitlines():
            if not self.line_is_relevant(line):
                continue
            for classifier in self.classifiers:
                name = classifier['name']
                for regex in classifier['regexes']:
                    for observable in re.findall(regex, line):
                        observable_name = classifier['prepare'](observable)
                        new_ob = ObservableObject(observable_name, Stix2.get_containerid(line), line, line[:31])
                        if new_ob.name and not Stix2.is_on_whitelist(new_ob.name):
                            final[name].add(new_ob)

        for classifier in self.classifiers:
            final[classifier["name"]] = sorted(list(final[classifier["name"]]))

        all_stix_groupings = []
        all_stix_objects = []
        for key, content in final.items():
            if key.startswith("files") and content:
                stix_grouping, stix_objects = Stix2.parse_observables_to_files(key, content)
                all_stix_groupings.append(stix_grouping)
                all_stix_objects.extend(stix_objects)
            elif key == "hosts_connected" and content:
                stix_grouping, stix_objects = Stix2.parse_hosts_to_ip_mac_addresses(key, content)
                all_stix_groupings.append(stix_grouping)
                all_stix_objects.extend(stix_objects)
            elif key == "processes_created" and content:
                stix_grouping, stix_objects = Stix2.parse_observables_to_processes(key, content)
                all_stix_groupings.append(stix_grouping)
                all_stix_objects.extend(stix_objects)
            elif key == "domains" and content:
                stix_grouping, stix_objects = Stix2.parse_observables_to_domains(key, content)
                all_stix_groupings.append(stix_grouping)
                all_stix_objects.extend(stix_objects)
        stix_malware_analysis = MalwareAnalysis(
            type="malware-analysis",
            product="cuckoo-sandbox",
            analysis_sco_refs=all_stix_objects
        )
        all_stix_objects.append(stix_malware_analysis)
        all_stix_objects.extend(all_stix_groupings)
        stix_bundle = Bundle(type="bundle",
                             id="bundle--" + str(uuid1()),
                             objects=all_stix_objects,
                             allow_custom=True)
        output_file = open(self.analysis_path + "/stix-file.json", "w")
        str_bundle = stix_bundle.serialize(pretty=False, indent=4)
        output_file.writelines(str_bundle)
        output_file.close()
