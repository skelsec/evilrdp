![Supported Python versions](https://img.shields.io/badge/python-3.7+-blue.svg) [![Twitter](https://img.shields.io/twitter/follow/skelsec?label=skelsec&style=social)](https://twitter.com/intent/follow?screen_name=skelsec)

:triangular_flag_on_post: This is the public repository of aardwolf, for latest version and updates please consider supporting us through https://porchetta.industries/

# EVILRDP - More control over RDP
Th evil twin of [`aardwolfgui`](https://github.com/skelsec/aardwolfgui) using the [`aardwolf`](https://github.com/skelsec/aardwolf) RDP client library that gives you extended control over the target and additional scripting capabilities from the command line.

## :triangular_flag_on_post: Sponsors

If you want to sponsors this project and have the latest updates on this project, latest issues fixed, latest features, please support us on https://porchetta.industries/

## Official Discord Channel

Come hang out on Discord!

[![Porchetta Industries](https://discordapp.com/api/guilds/736724457258745996/widget.png?style=banner3)](https://discord.gg/ycGXUxy)

# Features
 - Control mouse and keyboard in an automated way from command line
 - Control clipboard in an automated way from command line
 - Spawn a SOCKS proxy from the client that channels network communication to the target via RDP  
 - Execute arbitrary SHELL and PowerShell commands on the target without uploading files
 - Upload and download files to/from the target even when file transfers are disabled on the target

# Scripts
 - `evilrdp` - GUI + command line RDP client 

# Usage
After installing this package, a new executable will be available called `evilrdp`.  
Upon making a successful connection to the target you'll be presented with a GUI just like a normal RDP client as well as the command line from where you executed `evilrdp` will turn into an interactive shell.  
There will be two groups of commands available to you, as follows:  
- Commands that can be issues any time. This include commands like:
  - mousemove
  - rightclick
  - doubleclick
  - type
  - typefile
  - return/enter
  - invokerun
  - clipboardset
  - clipboardsetfile
  - clipboardget
  - powershell
  - screenshot
- Commands which only work when the `PSCMD` channel is established
  - pscmdchannel - Changes the `PSCMD` channel name from the default. Use this when you changed the channelname in agent script file
  - **startpscmd - This tries to automatically start the remote agent which allows further commands to be used**
  - pscmd - Executes a powershell command
  - getfile - Downloads remote file
  - shell - Executes a shell command
  - socksproxy - Starts a SOCKS4a/5 proxy

As it is with all things RDP, automatic command execution doesn't always work mostly because of timing issues therefore the `startpscmd` might need to be used 2 times, OR you might need to start the `PSCMD` channel manually.  
When `PSCMD` channel starts, you'll get a notification in your client shell.

# URL format
As usual the scripts take the target/scredentials in URL format. Below some examples
 - `rdp+kerberos-password://TEST\Administrator:Passw0rd!1@win2016ad.test.corp/?dc=10.10.10.2&proxytype=socks5&proxyhost=127.0.0.1&proxyport=1080`  
 CredSSP (aka `HYBRID`) auth using Kerberos auth + password via `socks5` to `win2016ad.test.corp`, the domain controller (kerberos service) is at `10.10.10.2`. The socks proxy is on `127.0.0.1:1080`
 - `rdp+ntlm-password://TEST\Administrator:Passw0rd!1@10.10.10.103`  
 CredSSP (aka `HYBRID`) auth using NTLM auth + password connecting to RDP server `10.10.10.103`
 - `rdp+ntlm-password://TEST\Administrator:<NThash>@10.10.10.103`  
 CredSSP (aka `HYBRID`) auth using Pass-the-Hash (NTLM) auth connecting to RDP server `10.10.10.103`
 - `rdp+plain://Administrator:Passw0rd!1@10.10.10.103`  
 Plain authentication (No SSL, encryption is RC4) using password connecting to RDP server `10.10.10.103`
 - See `-h` for more

# Kudos
 - Balazs Bucsay ([@xoreipeip](https://twitter.com/xoreipeip)) [`SocksOverRDP`](https://github.com/nccgroup/SocksOverRDP). The base idea for covert comms over RDP

