# LinuxDotnet
### Tools and solutions for using dotnet on linux and embedded linux

To create a new dotnet console application just use `./create_dotnet_app`

# Tools
### create_dotnet_app [bash]
Location: ./tools/create_dotnet_app
```
Usage: ./create_dotnet_app <Name> [directory=./]
Creates a new console application.
```
#### Example
```
cd $HOME
git clone git@github.com:balintt21/LinuxDotnet.git
mkdir /home/<user>/dotnet_apps
./LinuxDotnet/create_dotnet_app Example /home/<user>/dotnet_apps
./dotnet_apps/builder.py release
```
