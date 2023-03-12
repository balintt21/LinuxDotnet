#!/usr/bin/env python3

import sys, os, subprocess, re
from enum import Enum
import xml.etree.ElementTree as ET
import argparse


def system_has(program) -> bool:
    bin_dirs = os.environ.get("PATH").split(":")
    for dir in bin_dirs:
        if os.path.isdir(dir):
            run_res = subprocess.run(["find", dir, "-name", program], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if (run_res.returncode == 0) and run_res.stdout.decode("utf-8"):
                return True
    return False


class Logger:
    def __init__(self) -> None:
        self.log = ""

    def add_log_entry(self, log_tag, msg):
        self.log += f"[{log_tag}]: {msg}\n"

    def log_info(self, msg):
        self.add_log_entry("INFO", msg)

    def log_warn(self, msg):
        self.add_log_entry("WARN", msg)

    def log_error(self, msg):
        self.add_log_entry("ERROR", msg)

    def flush(self):
        if self.log:
            print(self.log)
            self.log = ""


class BuildMode(Enum):
    DEBUG = 0, "Debug"
    RELEASE = 1, "Release"

    def __new__(cls, value, name):
        member = object.__new__(cls)
        member._value_ = value
        member.fullname = name
        return member

    def __int__(self):
        return self.value


class BuildPlatform(Enum):
    HOST = 0, "host"
    X86_64 = 1, "linux-x64"
    ARM_64 = 2, "linux-arm64"
    ARM = 3, "linux-arm"

    def __new__(cls, value, name):
        member = object.__new__(cls)
        member._value_ = value
        member.fullname = name
        return member

    def __int__(self):
        return self.value


class Builder:
    def __init__(self, is_native_build = False, sysroot = "", install_dir = "") -> None:
        self.version = "1.0.0"
        self.is_valid = False
        self.root = os.path.dirname(sys.argv[0])
        self.dotnet_version = ""
        self.dotnet_major_version = ""
        self.project_name = os.path.basename(self.root)
        self.project_file = os.path.join(self.root, self.project_name + ".csproj")
        self.project_xml = None
        self.is_native_build = is_native_build
        self.sysroot = sysroot
        self.install_dir = install_dir
        self.publish_dir = ""
        self.logger = Logger()

        self.logger.log_info(f"builder version is {self.version}")

        if not os.path.isfile(self.project_file):
            self.logger.log_error("Missing .csproj file! Working directory has no dotnet project!")
        else:
            if system_has("dotnet"):
                run_res = subprocess.run(["dotnet", "--version"], stdout=subprocess.PIPE)
                if run_res.returncode == 0:
                    self.dotnet_version = run_res.stdout.decode("utf-8").removesuffix('\n')
                    if self.dotnet_version:
                        parts = self.dotnet_version.split(".")
                        if len(parts) > 2:
                            self.dotnet_major_version = parts[0] + "." + parts[1]
                            self.logger.log_info(f"dotnet version is net{self.dotnet_major_version} -> ({self.dotnet_version})")
                
                try:
                    self.project_xml = ET.parse(self.project_file)
                    xml_root = self.project_xml.getroot()
                    property_group = xml_root.find("./PropertyGroup")
                    if property_group != None:
                        publish_aot = property_group.find("./PublishAot")
                        if publish_aot == None:
                            publish_aot = ET.Element("PublishAot")
                            publish_aot.text = "true" if self.is_native_build else "false"
                            property_group.append(publish_aot)
                        else:
                            publish_aot.text = "true" if self.is_native_build else "false"

                        invariant_global = property_group.find("./InvariantGlobalization")
                        if invariant_global == None:
                            invariant_global = ET.Element("InvariantGlobalization")
                            invariant_global.text = "true" if self.is_native_build else "false"
                            property_group.append(invariant_global)
                        else:
                            invariant_global.text = "true" if self.is_native_build else "false"

                    else:
                        self.logger.log_error("invalid .csproj file! missing PropertyGroup")
                    with open (self.project_file, "wb") as file:
                        self.project_xml.write(file)

                    if self.install_dir and not os.path.isdir(self.install_dir):
                        if subprocess.run(["mkdir", "-p", self.install_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
                            self.logger.log_error(f"failed to create install directory: '{self.install_dir}'")
                            return

                    self.is_valid = True
                except:
                    self.logger.log_error("failed to parse .csproj file!")
            else:
                self.logger.log_error("dotnet runtime and sdk is missing! To install see https://learn.microsoft.com/en-us/dotnet/core/install/linux-ubuntu")
        
    

    def __bool__(self) -> bool:
        return self.is_valid


    def build(self, build_mode, target_platform) -> bool:
        if self.is_valid:
            command = ["dotnet", "publish", "-f", f"net{self.dotnet_major_version}", "--self-contained", "true", "-c", build_mode.fullname ]
            if int(target_platform) > int(BuildPlatform.HOST):
                if not system_has("clang"):
                    self.logger.log_error("clang is missing for cross compilation! Install clang! Ubunbtu: sudo apt install clang")
                    return False

                if self.is_native_build:
                    if not os.path.isdir(self.sysroot):
                        self.logger.log_error("sysroot is missing for cross compilation!")
                        return False
                    
                    command += ["-r", target_platform.fullname, "-p:CppCompilerAndLinker=clang", f"-p:SysRoot={self.sysroot}" ]

            self.logger.log_info(f"building {self.project_name}")
            debug_line = "executing:"
            for arg in command:
                debug_line += " " + arg
            self.logger.log_info(debug_line)
            self.logger.flush()

            returncode = 1
            with subprocess.Popen(command, cwd=self.root, stdout=subprocess.PIPE) as proc:
                line = proc.stdout.readline()
                while line:
                    parsed_line = line.decode("utf-8")[:-1]
                    print(parsed_line)
                    re_res = re.search(f"\s{self.project_name}\s->\s(.+publish\/)", parsed_line)
                    if re_res:
                        self.publish_dir = re_res.groups()[0]
                    line = proc.stdout.readline()
                returncode = proc.wait()

            if returncode != 0:
                self.logger.log_error("build failed!")
            elif self.install_dir and self.publish_dir:
                self.logger.log_info(f"installing to {self.install_dir}")
                if subprocess.run(["cp", "-af", os.path.join(self.publish_dir, "."), self.install_dir]).returncode != 0:
                    self.logger.log_error(f"failed to install application to {self.install_dir}")
            return returncode == 0
            


    def clean(self) -> bool:
        run_res = subprocess.run(["rm", "-rf", os.path.join(self.root, "bin"), os.path.join(self.root, "obj")], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        if run_res.returncode == 0:
            self.logger.log_info("clean was successful")
            return True
        else:
            self.logger.log_error("failed to clean project!")
            return False

    
    def log(self):
        self.logger.flush()


def build_release(builder) -> bool:
    return builder.build(BuildMode.RELEASE, BuildPlatform.HOST)


def build_debug(builder) -> bool:
    return builder.build(BuildMode.DEBUG, BuildPlatform.HOST)


def clean(builder):
    return builder.clean()

def build_release_arm64(builder)-> bool:
    return builder.build(BuildMode.RELEASE, BuildPlatform.ARM_64)


def build_debug_arm64(builder)-> bool:
    return builder.build(BuildMode.DEBUG, BuildPlatform.ARM_64)


def build_release_arm(builder)-> bool:
    return builder.build(BuildMode.RELEASE, BuildPlatform.ARM)


def build_debug_arm(builder)-> bool:
    return builder.build(BuildMode.DEBUG, BuildPlatform.ARM)

        
BUILD_OPTIONS = { "release" : build_release
                , "debug" : build_debug
                , "clean" : clean
                , "release:arm64" : build_release_arm64
                , "debug:arm64" : build_debug_arm64
                , "release:arm" : build_release_arm
                , "debug:arm" : build_debug_arm }


def print_help():
    usage = f"Usage: {sys.argv[0]} [OPTIONS] <BUILD_OPTION>\n"
    usage += "Description: Can build and publish self-contained and native dotnet application to several platforms\n\tself-contained: Deployable anywhere without dotnet-runtime\n\tnative: AOT(Ahead of Time/binary) Built into one executable and portable binary file\n"
    usage += "OPTIONS:\n" \
            "\t-h, --help - Prints this help message\n" \
            "\t-n, --native - Builds (AOT) native application (MAY require [SYSROOT_DIR])\n" \
            "\t-s, --sysroot - Sysroot for native cross compilation\n" \
            "\t                !! Required for cross-compilation when using --native option !!\n" \
            "\nPossible values for <BUILD_OPTION> are the following:\n"
    build_options_str = ""
    for bopt in BUILD_OPTIONS.keys():
        build_options_str += f"\t{bopt}\n"
    usage += build_options_str
    usage += "\nNOTE: Any cross platform build option used with '--native' option MAY require --sysroot <DIR>!"
    print(usage)



def main():
    arg_parser = argparse.ArgumentParser(add_help=False)
    arg_parser.add_argument("-h", "--help", action="store_true")
    arg_parser.add_argument("-n", "--native", action="store_true")
    arg_parser.add_argument("-s", "--sysroot", type=str, action="store", default="", nargs="?")
    arg_parser.add_argument("-i", "--install", type=str, action="store", default="", nargs="?")
    options, arguments = arg_parser.parse_known_args()

    if len(sys.argv) < 2 or options.help:
        print_help()
        return 0    
    
    build_option = arguments[0]
    sysroot = ""
    install_dir = ""
    is_native_build = ("-n" in sys.argv) or ("--native" in sys.argv)

    if options.install:
        install_dir = options.install

    if options.sysroot:
        sysroot = options.sysroot
        
    if build_option in BUILD_OPTIONS:
        builder = Builder(is_native_build, sysroot, install_dir)
        if builder:
            if BUILD_OPTIONS[build_option](builder):
                pass
            else:
                print("failure")
        builder.log()
    else:
        print(f"unrecognized option: '{build_option}'! See {sys.argv[0]} --help")
    

if __name__ == "__main__":
    main()