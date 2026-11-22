// core.js: run the shared core's command line for the MEGA extension.
// SPDX-License-Identifier: GPL-3.0-or-later

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

/**
 * Runs `megacmd-applet ARGS` from the core bundled in the folder CORE_DIR,
 * without a shell.
 *
 * Cancelling CANCELLABLE kills the process and rejects the promise with
 * Gio.IOErrorEnum.CANCELLED.
 *
 * @param {string} coreDir - folder holding the core's bin/ and core/
 * @param {string[]} args - the command line's arguments
 * @param {object} [options]
 * @param {string} [options.megacmdDir] - folder of MEGAcmd's commands, searched
 *   before the PATH; empty for the PATH alone
 * @param {Gio.Cancellable} [options.cancellable] - stops the process
 * @returns {Promise<{status: number, stdout: string, stderr: string}>} how it ended
 */
export function runCore(coreDir, args, {megacmdDir = '', cancellable = null} = {}) {
    const folder = megacmdDir ? [`--megacmd-dir=${megacmdDir}`] : [];
    const argv = ['python3', '-I', `${coreDir}/bin/megacmd-applet`, ...folder, ...args];
    const flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE;
    return new Promise((resolve, reject) => {
        let process;
        try {
            process = Gio.Subprocess.new(argv, flags);
        } catch (error) {
            reject(error);
            return;
        }
        const killId = cancellable ? cancellable.connect(() => process.force_exit()) : 0;
        process.communicate_utf8_async(null, cancellable, (source, result) => {
            if (killId)
                cancellable.disconnect(killId);
            try {
                const [, stdout, stderr] = source.communicate_utf8_finish(result);
                resolve({status: source.get_exit_status(), stdout: stdout ?? '', stderr: stderr ?? ''});
            } catch (error) {
                reject(error);
            }
        });
    });
}

/**
 * Tells whether ERROR comes from a cancelled operation.
 *
 * @param {Error} error - an error thrown by runCore or a Gio call
 * @returns {boolean} true when the operation was cancelled
 */
export function isCancelled(error) {
    return error instanceof GLib.Error && error.matches(Gio.IOErrorEnum, Gio.IOErrorEnum.CANCELLED);
}
