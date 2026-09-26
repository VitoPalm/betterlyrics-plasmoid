import QtQuick
import org.kde.plasma.plasma5support as P5Support

Item {
    id: root

    property string output: ""
    property var activeCommands: []

    signal exited(string cmd, int exitCode, int exitStatus, string stdout, string stderr)

    function run(cmd) {
        activeCommands = activeCommands.concat([cmd]);
        runCommand.exec(cmd);
    }

    function terminate(cmd) {
        runCommand.exit(cmd);
        activeCommands = activeCommands.filter(function(item) { return item !== cmd; });
    }

    function terminateAll() {
        const commands = activeCommands.slice(0);
        for (let i = 0; i < commands.length; i++) runCommand.exit(commands[i]);
        activeCommands = [];
    }

    P5Support.DataSource {
        id: runCommand

        function exec(cmd) {
            runCommand.connectSource(cmd);
        }

        function exit(cmd) {
            runCommand.disconnectSource(cmd);
        }

        engine: "executable"
        connectedSources: []
        onNewData: function (source, data) {
            var exitCode = data["exit code"] ?? -1;
            var exitStatus = data["exit status"] ?? -1;
            var stdout = data["stdout"] || "";
            var stderr = data["stderr"] || "";
            root.exited(source, exitCode, exitStatus, stdout, stderr);
            disconnectSource(source);
            root.activeCommands = root.activeCommands.filter(function(item) { return item !== source; });
        }
    }
}
