$VCHannelDef = @'
using System;
using System.Runtime.InteropServices;
using System.IO;
using System.Text;
using Microsoft.Win32.SafeHandles;
using System.ComponentModel;
using System.Threading.Tasks;
using System.Collections.Generic;
using System.Net.Sockets;
using System.Threading;

/// <summary>
/// The WtsApi32 class is taken from P/Invoke and other sources.
/// Most important part is the "Open" function which will return a fully functioning FileStream object for the given channel.
/// There is one caveat! One Read command will return at maxiumum 1600bytes (with the 8 byte header included) woth of data. This is 
/// by RDP protocol design, cannot be changed. The workaround is to design the communication protocol with an appropriate length field
/// so you'll know when each packet ends.
/// THIS WILL ONLY WORK FROM AN RDP SESSION. RUNNING THIS CODE OUTSIDE AN RDP SESSION WILL FAIL TO OPEN THE CHANNEL (OVBIOUSLY)
/// </summary>
class WtsApi32
{
    [Flags]
    public enum DuplicateOptions : uint
    {
        DUPLICATE_CLOSE_SOURCE = (0x00000001),// Closes the source handle. This occurs regardless of any error status returned.
        DUPLICATE_SAME_ACCESS = (0x00000002), //Ignores the dwDesiredAccess parameter. The duplicate handle has the same access as the source handle.
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr GetCurrentProcess();

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    static extern bool DuplicateHandle(IntPtr hSourceProcessHandle,
       IntPtr hSourceHandle, IntPtr hTargetProcessHandle, out IntPtr lpTargetHandle,
       uint dwDesiredAccess, [MarshalAs(UnmanagedType.Bool)] bool bInheritHandle, uint dwOptions);

    private enum WTS_VIRTUAL_CLASS
    {
        ClientData,  // Virtual channel client module data
        FileHandle   // (C2H data)
    };

    [DllImport("Wtsapi32.dll", SetLastError = true)]
    public static extern IntPtr WTSVirtualChannelOpen(IntPtr server,
        int sessionId, [MarshalAs(UnmanagedType.LPStr)] string virtualName);

    [DllImport("Wtsapi32.dll", CharSet = CharSet.Ansi, ExactSpelling = true, SetLastError = true)]
    private static extern IntPtr WTSVirtualChannelOpenEx(uint dwSessionID, string pChannelName, int flags);

    [DllImport("Wtsapi32.dll", SetLastError = true)]
    public static extern bool WTSVirtualChannelWrite(IntPtr channelHandle,
           byte[] buffer, int length, ref int bytesWritten);

    [DllImport("Wtsapi32.dll", SetLastError = true)]
    public static extern bool WTSVirtualChannelRead(IntPtr channelHandle,
           int timeout, byte[] buffer, int length, ref int bytesReaded);

    [DllImport("Wtsapi32.dll")]
    public static extern bool WTSVirtualChannelClose(IntPtr channelHandle);

    [DllImport("Wtsapi32.dll", SetLastError = true)]
    private static extern bool WTSVirtualChannelQuery(IntPtr hChannelHandle,
        WTS_VIRTUAL_CLASS virtualClass,
        ref IntPtr ppBuffer,
        ref uint pBytesReturned);

    [DllImport("Wtsapi32.dll", ExactSpelling = true, SetLastError = false)]
    public static extern void WTSFreeMemory(IntPtr memory);

    public static uint WTS_CURRENT_SESSION = uint.MaxValue;

    public enum WTS_CHANNEL_OPTION
    {
        DYNAMIC = 0x00000001,   // dynamic channel
        DYNAMIC_PRI_LOW = 0x00000000,   // priorities
        DYNAMIC_PRI_MED = 0x00000002,
        DYNAMIC_PRI_HIGH = 0x00000004,
        DYNAMIC_PRI_REAL = 0x00000006,
        DYNAMIC_NO_COMPRESS = 0x00000008
    }


    static public int CHANNEL_CHUNK_LENGTH = 1600;

    static public int WTS_CHANNEL_OPTION_DYNAMIC = 0x00000001;   // dynamic channel
    static public int WTS_CHANNEL_OPTION_DYNAMIC_PRI_LOW = 0x00000000;   // priorities
    static public int WTS_CHANNEL_OPTION_DYNAMIC_PRI_MED = 0x00000002;
    static public int WTS_CHANNEL_OPTION_DYNAMIC_PRI_HIGH = 0x00000004;
    static public int WTS_CHANNEL_OPTION_DYNAMIC_PRI_REAL = 0x00000006;
    static public int WTS_CHANNEL_OPTION_DYNAMIC_NO_COMPRESS = 0x00000008;

    /// <summary>
    /// Opens the virtual channel over RDP, and returns a FileStream object to read and write to the channel.
    /// Be careful, the recieved data (on FileStream.Read) will contain 8 bytes in the beginning which is the 
    /// header for the transmission layer, feel free to discard it!
    /// </summary>
    /// <param name="channelName"></param>
    /// <param name="option"></param>
    /// <returns></returns>
    /// <exception cref="Exception"></exception>
    /// <exception cref="Win32Exception"></exception>
    public static FileStream Open(string channelName, WTS_CHANNEL_OPTION option = WTS_CHANNEL_OPTION.DYNAMIC | WTS_CHANNEL_OPTION.DYNAMIC_NO_COMPRESS)
    {
        // Open
        
        IntPtr ppFile;
        IntPtr sfh = WTSVirtualChannelOpenEx(WTS_CURRENT_SESSION, channelName, (int)option);
        try
        {
            if(sfh == IntPtr.Zero)
            {
                int error = Marshal.GetLastWin32Error();
                throw new Exception("Failed to open channel! Code: " + error);
            }
            IntPtr pBuffer = IntPtr.Zero;
            try
            {
                uint cbReturned = 0;
                if (!WTSVirtualChannelQuery(sfh, WTS_VIRTUAL_CLASS.FileHandle, ref pBuffer, ref cbReturned)
                    || cbReturned < IntPtr.Size)
                {
                    throw new Win32Exception();
                }
                var pWtsFile = Marshal.ReadIntPtr(pBuffer);
                if (!DuplicateHandle(
                    GetCurrentProcess(), pWtsFile,
                    GetCurrentProcess(), out ppFile,
                    0, false, (uint)DuplicateOptions.DUPLICATE_SAME_ACCESS))
                {
                    throw new Win32Exception();
                }
            }
            finally
            {
                WTSFreeMemory(pBuffer);
            }
        }
        finally
        {

        }
        SafeFileHandle pFile = new SafeFileHandle(ppFile, true);
        // create
        return new FileStream(pFile, FileAccess.ReadWrite, bufferSize: 32 * 1024 * 1024, isAsync: true);
    }
}

/// <summary>
/// Type enum for each packet.
/// </summary>
public enum CMDType : int
{
    OK = 0,
    ERR = 1,
    CONTINUE = 2,
    PS = 20,
    GETFILE = 21,
    PUTFILE = 22,
    FILEDATA = 23,
    SHELL = 24,
    SHELLDATA = 25,
    SOCKETOPEN = 26,
    SOCKETDATA = 27,
}

/// <summary>
/// Packet class for the communication channel between the server and client component
/// Every packet contains this header, the data array structure depends on the CMDType
/// </summary>
public class CMD
{
    public int length;
    public byte[] token;
    public CMDType command;
    public byte[] data;

    public CMD(byte[]token, CMDType command, byte[]data)
    {
        this.token = token;
        this.command = command;
        this.data = data;
        this.length = data.Length + 24;

    }

    /// <summary>
    /// Parses the recieved bytes and returns the Packet.
    /// </summary>
    /// <param name="rawdata"></param>
    public CMD(byte[] rawdata)
    {
        this.length = (Int32)(BitConverter.ToInt16(rawdata, 0));
        this.token = new byte[16];
        Array.Copy(rawdata, 4, this.token, 0, 16);
        this.command = (CMDType)(Int32)(BitConverter.ToInt16(rawdata, 20));
        if (rawdata.Length > 24 ) {
            this.data = new byte[rawdata.Length - 24];
            Array.Copy(rawdata, 24, this.data, 0, rawdata.Length - 24);
        }

    }

    /// <summary>
    /// Serializes the packet to be sent over the channel.
    /// </summary>
    /// <returns></returns>
    public byte[] toBytes()
    {
        byte[] res = null;
        using (MemoryStream ms = new MemoryStream())
        {
            ms.Write(BitConverter.GetBytes(this.length), 0, 4);
            ms.Write(this.token, 0, this.token.Length);
            ms.Write(BitConverter.GetBytes((int)this.command), 0, 4);
            if(this.data.Length > 0)
            {
                ms.Write(this.data, 0, this.data.Length);
            }
            
            res = ms.ToArray();
        }
        return res;

    }
}

/// <summary>
/// Base class for the subchannels, this is part of the communication framework, not RDP.
/// Every time a command with an unknown token arrives from the RDP client, a new SubChannel is created.
/// </summary>
public class SubChannel
{
    protected VChannel manager;
    protected byte[] token;
    protected CMD initCmd;
    protected CancellationTokenSource channelClose;

    public SubChannel(VChannel manager, CMD initCmd, CancellationToken managerClose)
    {
        this.manager = manager;
        this.initCmd = initCmd;
        this.channelClose = CancellationTokenSource.CreateLinkedTokenSource(managerClose);
    }

    virtual public async Task start()
    {

    }

    virtual public async Task HandleIncoming(CMD cmd)
    {

    }
}

/// <summary>
/// This subchannel type is to manage file read operation.
/// Upon start, the whole file specificed by the filepath in the initCmd's data array 
/// will be read and transmitted back to the client.
/// </summary>
public class FileReadSubChannel : SubChannel
{
    string filepath;
    public FileReadSubChannel(VChannel manager, CMD initCmd, CancellationToken managerClose) : base(manager, initCmd, managerClose)
    {
        this.filepath = Encoding.UTF8.GetString( initCmd.data);

    }

    public override async Task start()
    {
        readFile();
    }

    async Task readFile()
    {
        try
        {
            using (var inFileSteam = new FileStream(filepath, FileMode.Open))
            {
                while(inFileSteam.Length != inFileSteam.Position)
                {
                    byte[] buffer = new byte[1500];
                    int bytesRead = await inFileSteam.ReadAsync(buffer, 0, buffer.Length, channelClose.Token);
                    await manager.SendCmd(initCmd.token, CMDType.FILEDATA, buffer);
                }
                
            }
            await manager.SendCmd(initCmd.token, CMDType.OK);
            return;
        }
        catch (Exception)
        {
            //cant put await in catch block...
            //what is this lunacy...
        }
        await manager.SendCmd(initCmd.token, CMDType.ERR);
    }

    public override async Task HandleIncoming(CMD cmd)
    {
        switch (cmd.command)
        {
            case CMDType.OK:
            case CMDType.ERR:
                {
                    channelClose.Cancel();
                    break;
                }
        }
    }
}

public class FileWriteSubChannel : SubChannel
{
    string filepath;
    FileStream fs;

    public FileWriteSubChannel(VChannel manager, CMD initCmd, CancellationToken managerClose) : base(manager, initCmd, managerClose)
    {
        this.filepath = Encoding.UTF8.GetString(initCmd.data);
    }

    public override async Task start()
    {
        fs = new FileStream(filepath, FileMode.Create, FileAccess.Write);
    }

    public override async Task HandleIncoming(CMD cmd)
    {
        switch (cmd.command)
        {
            case CMDType.FILEDATA:
                {
                    await fs.WriteAsync(cmd.data, 0, cmd.data.Length, channelClose.Token);
                    break;
                }
            case CMDType.OK:
            case CMDType.ERR:
                {
                    channelClose.Cancel();
                    fs.Close();
                    fs.Dispose();
                    break;
                }
        }
        
    }

}

/// <summary>
/// This SubChannel is created to manage one-shot style execution of shell commands
/// The STDOUT and STDERR data will be sent back to the RDP client, each with a different ID.
/// </summary>
public class CMDExecSubChannel : SubChannel
{
    string command;
    System.Diagnostics.Process process;
    public CMDExecSubChannel(VChannel manager, CMD initCmd, CancellationToken managerClose) : base(manager, initCmd, managerClose)
    {
        this.command = Encoding.UTF8.GetString(initCmd.data);
    }

    public override async Task start()
    {
        procreader();
    }

    async Task procreader()
    {
        try
        {
            System.Diagnostics.ProcessStartInfo procStartInfo = new System.Diagnostics.ProcessStartInfo("cmd", "/c " + command);
            procStartInfo.RedirectStandardOutput = true;
            procStartInfo.RedirectStandardError = true;
            procStartInfo.UseShellExecute = false;
            procStartInfo.CreateNoWindow = true;
            process = new System.Diagnostics.Process();
            process.StartInfo = procStartInfo;
            process.Start();

            while (!process.HasExited)
            {
                string result = process.StandardOutput.ReadToEnd();
                if (result.Length > 0)
                {
                    byte[] xxx = Encoding.UTF8.GetBytes(result);
                    byte[] data = new byte[4 + xxx.Length];
                    Array.Copy(BitConverter.GetBytes(1), data, 4);
                    Array.Copy(xxx, 0, data, 4, xxx.Length);
                    await manager.SendCmd(initCmd.token, CMDType.SHELLDATA, data);
                }
                string errresult = process.StandardError.ReadToEnd();
                if (result.Length > 0)
                {
                    byte[] xxx = Encoding.UTF8.GetBytes(errresult);
                    byte[] data = new byte[4 + xxx.Length];
                    Array.Copy(BitConverter.GetBytes(2), data, 4);
                    Array.Copy(xxx, 0, data, 4, xxx.Length);
                    await manager.SendCmd(initCmd.token, CMDType.SHELLDATA, data);
                }

            }

            await manager.SendCmd(initCmd.token, CMDType.OK);
            return;
        }
        catch (Exception objException)
        {
            //?????????
        }
        await manager.SendCmd(initCmd.token, CMDType.ERR);
    }

    public override async Task HandleIncoming(CMD cmd)
    {
        
    }


}

/// <summary>
/// SubChannel manages a remote SOCKS server. 
/// This is not a SOCKS server implementation, rather a simple wrapper around a single socket.
/// The actual SOCKS proxy is implemented on the remote end.
/// </summary>
public class SOCKSSubChannel : SubChannel
{
    string hostname;
    int port;
    int connect_or_bind;
    NetworkStream stream;
    TcpClient client;
    TcpListener listener;

    public SOCKSSubChannel(VChannel manager, CMD initCmd, CancellationToken managerClose) : base(manager, initCmd, managerClose)
    {
        this.connect_or_bind = BitConverter.ToInt32(initCmd.data, 0);
        this.port = BitConverter.ToInt32(initCmd.data, 4);
        this.hostname = Encoding.UTF8.GetString(initCmd.data, 8, initCmd.data.Length - 8);
    }

    public override async Task start()
    {
        startComms();
        
    }

    async Task startComms()
    {
        if (connect_or_bind == 1)
        {
            client = new TcpClient();
            await client.ConnectAsync(hostname, port);
            stream = client.GetStream();
            await manager.SendCmd(initCmd.token, CMDType.CONTINUE);

            while (true)
            {
                byte[] buffer = new byte[1500];
                int recvSize = await stream.ReadAsync(buffer, 0, buffer.Length, channelClose.Token);
                byte[] recdata = new byte[recvSize];
                Array.Copy(buffer, recdata, recdata.Length);
                await manager.SendCmd(initCmd.token, CMDType.SOCKETDATA, recdata);
            }
            
        }
        else
        {
            listener = new TcpListener(port);
            client = await listener.AcceptTcpClientAsync();
            stream = client.GetStream();
            await manager.SendCmd(initCmd.token, CMDType.CONTINUE);

            while (true)
            {
                byte[] buffer = new byte[1500];
                int recvSize = await stream.ReadAsync(buffer, 0, buffer.Length, channelClose.Token);
                byte[] recdata = new byte[recvSize];
                Array.Copy(buffer, recdata, recdata.Length);
                await manager.SendCmd(initCmd.token, CMDType.SOCKETDATA, recdata);
            }
        }


    }

    public override async Task HandleIncoming(CMD cmd)
    {
        switch (cmd.command)
        {
            case CMDType.SOCKETDATA:
                {
                    await stream.WriteAsync(cmd.data, 0, cmd.data.Length, channelClose.Token);
                    break;
                }
            case CMDType.OK:
            case CMDType.ERR:
                {
                    channelClose.Cancel();
                    stream.Close();
                    client.Close();
                    if(connect_or_bind != 1)
                    {
                        listener.Stop();
                    }

                    break;
                }
        }
    }

}

/// <summary>
/// This class manages the Virtual Dynamic channel over the RDP connection.
/// The channelname parameter must be known to the client, and by documentation should be max 7 ASCII characters long.
/// All communication between the RDP client component and this manager is done over the FileStream object provided by 
/// the WtsApi32 class.
/// This class contains and eventhandler called psCommandExec which can be used to execute PowerShell commands, if you start
/// it with the appropriate powershell setup (included in a separate script)
/// </summary>
public class VChannel
{
    public string channelname;
    private FileStream vchannel;
    public event EventHandler psCommandExec;
    private Dictionary<string, SubChannel> channels = new Dictionary<string, SubChannel>();
    private CancellationTokenSource cts = new CancellationTokenSource();

    public class PSExecEventArgs : EventArgs
    {
        public byte[] token { get; set; }
        public string cmd { get; set; }
        public VChannel channel { get; set; }
    }

    /// <summary>
    /// Powershell exec event trigger
    /// </summary>
    /// <param name="e"></param>
    protected virtual void OnPsExecCmd(PSExecEventArgs e)
    {
        if (psCommandExec == null) return;
        psCommandExec.Invoke(this, e);
    }


    /// <summary>
    /// Channel name MUST be the same on both the server and the client!
    /// </summary>
    /// <param name="channelname"></param>
    public VChannel(string channelname)
    {
        this.channelname = channelname;

    }

    /// <summary>
    /// This is the "main" function which will "block" until the RDP virtual channel is closed.
    /// </summary>
    /// <returns></returns>
    public async Task run()
    {
        vchannel = WtsApi32.Open(channelname, WtsApi32.WTS_CHANNEL_OPTION.DYNAMIC | WtsApi32.WTS_CHANNEL_OPTION.DYNAMIC_NO_COMPRESS);
        await HandleIncoming(vchannel);
    }

    /// <summary>
    /// When an unknown token arrives, a new Subchannel is opened based on the CMDType of the initiator cmd.
    /// Extend this switch-case for more features.
    /// </summary>
    /// <param name="cmd"></param>
    /// <returns></returns>
    async Task<SubChannel> startChannel(CMD cmd)
    {
        SubChannel channel = null;
        try
        {
            switch (cmd.command)
            {
                case CMDType.GETFILE:
                    {
                        channel = new FileReadSubChannel(this, cmd, this.cts.Token);
                        await channel.start();
                        break;
                    }
                case CMDType.SOCKETOPEN:
                    {
                        channel = new SOCKSSubChannel(this, cmd, cts.Token);
                        await channel.start();
                        break;
                    }
                case CMDType.SHELL:
                    {
                        channel = new CMDExecSubChannel(this, cmd, cts.Token);
                        await channel.start();
                        break;
                    }
                case CMDType.PUTFILE:
                    {
                        channel = new FileWriteSubChannel(this, cmd, cts.Token);
                        await channel.start();
                        break;
                    }
                default:
                    {
                        //unknown channel type!
                        throw new Exception("Unknown channel type!");
                        break;
                    }
            }
            return channel;
        }
        catch(Exception e)
        {
            
        }
        await SendCmd(cmd.token, CMDType.ERR);
        return channel;

    }

    /// <summary>
    /// This function is invoked whenever a new packet arrives from the remote client.
    /// Here you can see that the PS packet is special, as it triggers an event for PowerShell execution.
    /// Other packets (named cmd) are either kickstart a new subchannel, or get dispatched to an existing subchannel,
    /// </summary>
    /// <param name="cmd"></param>
    /// <returns></returns>
    async Task HandleCmd(CMD cmd)
    {
        switch (cmd.command)
        {
            case CMDType.PS:
                {
                    // Powershell execution, triggering event to be recieved by powershell
                    PSExecEventArgs e = new PSExecEventArgs();
                    e.token = cmd.token;
                    e.cmd = Encoding.UTF8.GetString(cmd.data);
                    e.channel = this;
                    OnPsExecCmd(e);
                    break;
                }
            default:
                {
                    // C# can't handle byte array in switch-case it seems
                    // converting the token to hex string ://
                    string tokenhex = BitConverter.ToString(cmd.token); //this is so stupid...
                    SubChannel ch;

                    if (!channels.TryGetValue(tokenhex, out ch))
                    {
                        // New command! Creating subchannel for it
                        ch = await startChannel(cmd);
                        channels.Add(tokenhex, ch);

                    }
                    else
                    {
                        // Dispatching packet to existing subchannel
                        ch.HandleIncoming(cmd);
                    }
                    break;
                }
        }
    }

    // Powershell can call this function with the results
    async public Task SendPSResult(string result, byte[] token)
    {
        await SendCmd(token, CMDType.OK, Encoding.UTF8.GetBytes(result));
    }

    /// <summary>
    /// Send a packet back to the RDP client.
    /// </summary>
    /// <param name="token"></param>
    /// <param name="cmdtype"></param>
    /// <returns></returns>
    async public Task SendCmd(byte[] token, CMDType cmdtype)
    {
        await SendCmd(token, cmdtype, new byte[0]);
    }

    /// <summary>
    /// Send a packet back to the RDP client.
    /// </summary>
    /// <param name="token"></param>
    /// <param name="cmdtype"></param>
    /// <returns></returns>
    async public Task SendCmd(byte[] token, CMDType cmdtype, byte[] data)
    {
        CMD res = new CMD(token, cmdtype, data);
        byte[] raw = res.toBytes();
        await vchannel.WriteAsync(raw, 0, raw.Length);
    }

    /// <summary>
    /// Start recieving the packets from the RDP client.
    /// This does the defragmenting, as there is a hard limit on the maximal data size per each ReadAsync call.
    /// </summary>
    /// <param name="vchannel"></param>
    /// <returns></returns>
    async Task HandleIncoming(FileStream vchannel)
    {
        int cmdlen = -1;
        MemoryStream ms = new MemoryStream();
        while (true)
        {
            while(!((cmdlen != -1) && cmdlen <= ms.Position))
            {
                byte[] buffer = new byte[4096];
                int bytesRead = await vchannel.ReadAsync(buffer, 0, buffer.Length);
                ms.Write(buffer, 8, bytesRead - 8);
                if(cmdlen == -1)
                {
                    cmdlen = (Int32)(BitConverter.ToInt32(buffer, 8));
                }
                
            }

            byte[] rawcmd = new byte[cmdlen];
            Array.Copy(ms.ToArray(), rawcmd, cmdlen);
            if (cmdlen != ms.Position)
            { 
                byte[] remainingBytes = new byte[ms.Position - cmdlen];
                Array.Copy(ms.ToArray(), ms.Position - cmdlen, remainingBytes, 0, ms.Position - cmdlen);
                ms.Dispose();
                ms = new MemoryStream(remainingBytes);
                if(remainingBytes.Length >= 4)
                {
                    cmdlen = BitConverter.ToInt32(remainingBytes, 0);
                }
            }
            else
            {
                ms.Dispose();
                ms = new MemoryStream();
                cmdlen = -1;
            }
            
            await HandleCmd(new CMD(rawcmd));            
        }
    }

}
'@


function Wait-Task {
    param(
        [Parameter(Mandatory, ValueFromPipeline)]
        [System.Threading.Tasks.Task[]]$Task
    )

    Begin {
        $Tasks = @()
    }

    Process {
        $Tasks += $Task
    }

    End {
        While (-not [System.Threading.Tasks.Task]::WaitAll($Tasks, 200)) {}
        $Tasks.ForEach( { $_.GetAwaiter().GetResult() })
    }
}

Set-Alias -Name await -Value Wait-Task -Force
Add-Type -TypeDefinition $VCHannelDef -IgnoreWarnings

$action = {
    #Write-Host $eventargs.cmd
    $outtext = ""
    Invoke-Expression -Command $eventargs.cmd | Tee-Object -Variable outtext
    await $eventargs.channel.SendPSResult($outtext, $eventargs.token);

}

$vc = [VChannel]::new("PSCMD")
$job = Register-ObjectEvent -InputObject $vc -EventName 'psCommandExec' -Action $action

await $vc.run();
