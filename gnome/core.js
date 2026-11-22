// core.js: run the shared core's command line for the MEGA extension.
// SPDX-License-Identifier: GPL-3.0-or-later

import Gio from 'gi://Gio';

/**
 * Runs `megacmd-applet ARGS` from the core bundled in the folder CORE_DIR,
 * without a shell.
 *
 * @param {string} coreDir - folder holding the core's bin/ and core/
 * @param {string[]} args - the command line's arguments
 * @param {Gio.Cancellable} [cancellable] - stops waiting for the result
 * @returns {Promise<{status: number, stdout: string, stderr: string}>} how it ended
 */
export function runCore(coreDir, args, cancellable = null) {
    const argv = ['python3', '-I', `${coreDir}/bin/megacmd-applet`, ...args];
    const flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE;
    return new Promise((resolve, reject) => {
        let process;
        try {
            process = Gio.Subprocess.new(argv, flags);
        } catch (error) {
            reject(error);
            return;
        }
        process.communicate_utf8_async(null, cancellable, (source, result) => {
            try {
                const [, stdout, stderr] = source.communicate_utf8_finish(result);
                resolve({status: source.get_exit_status(), stdout: stdout ?? '', stderr: stderr ?? ''});
            } catch (error) {
                reject(error);
            }
        });
    });
}
