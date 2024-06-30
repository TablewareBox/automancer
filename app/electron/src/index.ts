import 'source-map-support/register';

import electron, { BrowserWindow, dialog, Menu, MenuItemConstructorOptions, session, shell } from 'electron';
import { ok as assert } from 'node:assert';
import crypto from 'node:crypto';
import fsSync from 'node:fs';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { MenuDef, MenuEntryId } from 'pr1';
import { AppData, BridgeTcp, CertificateFingerprint, DraftEntryId, fsExists, HostSettings, HostSettingsId, PythonInstallationRecord, runCommand, searchForAdvertistedHosts, ServerConfiguration, SocketClientBackend } from 'pr1-library';
import { defer, Lock } from 'pr1-shared';
import * as uol from 'uol';

import { FileManager } from './file-manager';
import { HostWindow } from './host';
import { Disposable, DocumentChange, DraftSkeleton, IPC2d as IPCServer2d } from './interfaces';
import { rootLogger } from './logger';
import type { IPCEndpoint } from './shared/preload';
import { StartupWindow } from './startup';
import * as util from './util';


const ProtocolFileFilters = [
  { name: 'Protocols', extensions: ['yml', 'yaml'] }
];


export class CoreApplication {
  static version = 2;

  private disposables = new Set<Disposable>();
  private logger = rootLogger.getChild('application');
  private pool = new util.Pool(this.logger);

  private electronApp: electron.App;
  private quitting: boolean;

  private data!: AppData;
  private pythonInstallations!: PythonInstallationRecord;

  private appLogsDirPath: string;
  private dataDirPath: string;
  private dataLock = new Lock();
  private dataPath: string;
  private hostsDirPath: string;
  public hostsLogsDirPath: string;
  private logWritePromise: Promise<void> | null = null;
  private logsDirPath: string;

  private hostWindows: Record<HostSettingsId, HostWindow> = {};
  private startupWindow: StartupWindow | null = null;

  constructor(electronApp: electron.App) {
    this.electronApp = electronApp;
    this.quitting = false;

    let userData = this.electronApp.getPath('userData');

    this.dataDirPath = path.join(userData, 'App Data');
    this.dataPath = path.join(this.dataDirPath, 'app.json');

    this.hostsDirPath = path.join(userData, 'App Hosts');

    this.logsDirPath = this.electronApp.getPath('logs');
    this.appLogsDirPath = path.join(this.logsDirPath, 'app');
    this.hostsLogsDirPath = path.join(this.logsDirPath, 'hosts');


    this.electronApp.on('before-quit', () => {
      this.quitting = true;
    });


    let quit = false;

    this.electronApp.on('will-quit', (event) => {
      if (quit) {
        return;
      }

      event.preventDefault();

      this.logger.debug('Trying to quit');

      (async () => {
        // The check for this.pool.empty is only for the first iteration
        while (!this.pool.empty || (this.disposables.size > 0)) {
          for (let disposable of this.disposables) {
            this.pool.add(async () => void await disposable.dispose());
          }

          this.disposables.clear();

          this.logger.debug(`Waiting for ${this.pool.size} tasks to settle`);
          await this.pool.wait();
        }

        this.logger.debug('Quitting');

        rootLogger.end();
        await this.logWritePromise;
      })()
        .catch((err) => {
          console.error(err);
        })
        .finally(() => {
          quit = true;
          this.electronApp.quit();
        });
    });

    this.electronApp.on('window-all-closed', () => {

    });

    this.electronApp.on('second-instance', () => {
      this.createStartupWindow();
    });

    this.electronApp.on('certificate-error', (event, webContents, url, error, certificate, callback, isMainFrame) => {
      let browserWindow = BrowserWindow.fromWebContents(webContents)!;
      let hostWindow = Object.values(this.hostWindows).find((hostWindow) => (hostWindow.browserWindow === browserWindow))!;

      let hostSettings = hostWindow.hostSettings;

      if ((error === 'net::ERR_CERT_AUTHORITY_INVALID') && (hostSettings.options.type === 'tcp') && hostSettings.options.secure) {
        let prefix = 'sha256/';
        let rawFingerprint = certificate.fingerprint;

        if (rawFingerprint.startsWith(prefix)) {
          let fingerprint = Buffer.from(rawFingerprint.slice(prefix.length), 'base64').toString('hex') as CertificateFingerprint;

          if (fingerprint === hostSettings.options.fingerprint) {
            event.preventDefault();
            callback(true);
            return;
          }
        }
      }

      callback(false);
    });


    rootLogger
      .use(uol.format())
      .pipe(new uol.ConcatTransformer())
      .pipe(process.stderr);


    if (process.platform === 'darwin') {
      Menu.setApplicationMenu(Menu.buildFromTemplate([
        { role: 'appMenu' },
        { role: 'editMenu' },
        {
          label: 'View',
          submenu: [
            { label: 'Open startup menu',
              click: () => {
                this.createStartupWindow();
              } },
            { type: 'separator' },
            { label: 'Reveal data directory in explorer',
              click: () => {
                shell.showItemInFolder(this.dataDirPath);
              } },
            { label: 'Reveal logs directory in explorer',
              click: () => {
                shell.showItemInFolder(this.logsDirPath);
              } },
            { type: 'separator' },
            { role: 'reload' },
            { role: 'toggleDevTools' }
          ]
        },
        { role: 'windowMenu' },
        { role: 'help' },
        {
          role: 'help',
          submenu: [
            { label: 'Documentation' }
          ]
        }
      ]));
    }
  }

  get debug() {
    let envValue = process.env['DEBUG'];
    return (!this.electronApp.isPackaged && (envValue !== '0')) || (envValue === '1');
  }

  async createStartupWindow() {
    if (this.startupWindow) {
      this.startupWindow.focus();
    } else {
      this.startupWindow = new StartupWindow(this);

      this.pool.add(async () => {
        await this.startupWindow!.closed;
        this.startupWindow = null;

        if (!this.quitting && (Object.keys(this.hostWindows).length < 1)) {
          this.electronApp.quit();
        }
      });
    }
  }

  async createHostWindow(hostSettings: HostSettings) {
    let hostWindow = new HostWindow(this, hostSettings);
    this.hostWindows[hostSettings.id] = hostWindow;

    this.pool.add(async () => {
      await hostWindow.closed;
      delete this.hostWindows[hostSettings.id];

      if (!this.quitting) {
        this.createStartupWindow();
      }
    });
  }

  async initialize() {
    if (!this.electronApp.requestSingleInstanceLock()) {
      this.electronApp.quit();
      return;
    }

    this.logger.debug(`Running process with id ${process.pid}`);
    this.logger.debug(`Running Node.js ${process.version}`);
    this.logger.debug(`Running Electron ${process.versions.electron}`);
    this.logger.debug(`Running Chrome ${process.versions.chrome}`);
    this.logger.debug(`Running on platform ${os.platform()} ${os.release()} / ${os.arch()}`);

    await fs.mkdir(this.appLogsDirPath, { recursive: true });
    let appLogFilePath = path.join(this.appLogsDirPath, `${Date.now()}.log`);

    let logWriteStream = rootLogger
      .use(uol.format('%(LevelName) :: %(namespace) :: %(message)'))
      .pipe(new uol.ConcatTransformer())
      .pipe(fsSync.createWriteStream(appLogFilePath));

    this.logWritePromise = new Promise<void>(async (resolve, reject) => {
      logWriteStream.on('error', (err) => void reject(err));
      logWriteStream.on('finish', () => void resolve());
    }).catch((err) => {
      if (!this.logger.closed) {
        this.logger.error(err.message);
      } else {
        console.error(err.message);
      }
    });


    this.pythonInstallations = await util.findPythonInstallations();

    await this.electronApp.whenReady();

    session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
      if (details.webContents) {
        let browserWindow = BrowserWindow.fromWebContents(details.webContents)!;
        let hostWindow = Object.values(this.hostWindows).find((hostWindow) => (hostWindow.browserWindow === browserWindow)) ?? null;
        let staticUrl = hostWindow?.client?.info?.staticUrl ?? null;

        if (staticUrl !== null) {
          let origin = new URL(staticUrl).origin;

          callback({
            responseHeaders: {
              ...details.responseHeaders,
              'Content-Security-Policy': [`script-src 'self' ${origin} 'nonce-71e54eb8'`]
            }
          });
        } else {
          callback({});
        }
      } else {
        callback({});
      }
    });

    this.logger.info(`Loading data from ${this.dataDirPath}`);
    await this.loadData();

    if (!this.data) {
      this.logger.debug('Aborting initialization');
      this.electronApp.quit();

      return;
    }

    this.logger.info('Initialized');


    let ipcMain = electron.ipcMain as IPCServer2d<IPCEndpoint>;


    // Window management

    ipcMain.on('main.ready', (event) => {
      BrowserWindow.fromWebContents(event.sender)!.show();
    });


    // Context menu creation

    // @ts-expect-error
    ipcMain.handle('main.triggerContextMenu', async (event, menu, position) => {
      let deferred = defer<MenuEntryId[] | null>();

      let createAppMenuFromMenu = (menu: MenuDef, ancestors: MenuEntryId[] = []) => {
        let menuItems: MenuItemConstructorOptions[] = [];

        for (let entry of menu) {
          let path = [...ancestors, entry.id].flat();

          switch (entry.type) {
            case undefined:
            case 'option': {
              menuItems.push({
                checked: !!entry.checked,
                type: entry.checked ? 'checkbox' : 'normal',
                enabled: !entry.disabled,
                label: entry.name,
                click: () => void deferred.resolve(path)
              });

              break;
            }

            case 'divider': {
              menuItems.push({
                type: 'separator'
              });

              break;
            }

            case 'header': {
              if (menuItems.length > 0) {
                menuItems.push({
                  type: 'separator'
                });
              }

              menuItems.push({
                label: entry.name,
                enabled: false
              });

              break;
            };
          }
        }

        return electron.Menu.buildFromTemplate(menuItems);
      };

      let appMenu = createAppMenuFromMenu(menu);

      appMenu.popup({
        callback: () => void deferred.resolve(null),
        x: position.x,
        y: position.y,
        window: BrowserWindow.fromWebContents(event.sender)!
      });

      return await deferred.promise;
    });


    // Host settings management

    ipcMain.handle('hostSettings.addRemoteHost', async (_event, options) => {
      let hostSettingsId = crypto.randomUUID() as HostSettingsId;

      await this.setData({
        hostSettingsRecord: {
          ...this.data.hostSettingsRecord,
          [hostSettingsId]: {
            id: hostSettingsId,
            label: options.label,
            options: {
              type: 'tcp',
              ...options.options
            }
          } satisfies HostSettings
        }
      });

      return {
        hostSettingsId
      };
    });

    ipcMain.handle('hostSettings.displayCertificateOfRemoteHost', async (event, options) => {
      let result = await SocketClientBackend.test({
        address: {
          host: options.hostname,
          port: options.port
        },
        tls: {
          serverCertificateCheck: true,
          serverCertificateFingerprint: options.fingerprint
        }
      });

      if (result.ok || (result.reason === 'untrusted_server')) {
        await electron.dialog.showCertificateTrustDialog(BrowserWindow.fromWebContents(event.sender)!, {
          certificate: util.transformCertificate(result.tlsInfo!.certificate),
          message: `Certificate of host with address ${options.hostname}:${options.port}`
        });
      } else {
        this.logger.error('Failed to show remote host certificate');
      }
    });

    ipcMain.handle('hostSettings.testRemoteHost', async (_event, options) => {
      this.logger.debug(`Trying to connect to '${options.hostname}:${options.port}'`);

      let result = await SocketClientBackend.test({
        address: {
          host: options.hostname,
          port: options.port
        },
        tls: options.secure
          ? {
            serverCertificateCheck: !options.trusted,
            serverCertificateFingerprint: options.fingerprint
          }
          : null
      });

      if ('tlsInfo' in result) {
        let { tlsInfo, ...rest } = result;

        return {
          ...rest,
          fingerprint: tlsInfo?.fingerprint ?? null
        };
      }

      return result;
    });

    ipcMain.handle('hostSettings.createLocalHost', async (_event, options) => {
      let pythonInstallation = options.customPythonInstallation ?? this.pythonInstallations[options.pythonInstallationSettings.id];

      let hostSettingsId = crypto.randomUUID() as HostSettingsId;
      let hostDirPath = path.join(this.hostsDirPath, hostSettingsId);
      let envPath = path.join(hostDirPath, 'env');

      let architecture = options.pythonInstallationSettings.architecture;
      let pythonPath = pythonInstallation.path;

      this.logger.info(`Creating local host with settings id '${hostSettingsId}'`);
      this.logger.debug('Creating host directory');

      let conf;

      try {
        await fs.mkdir(hostDirPath, { recursive: true });

        let requirementsFilePath = path.join(hostDirPath, 'requirements.in');
        await fs.writeFile(requirementsFilePath, await fs.readFile(path.join(util.getResourcePath(), 'base-requirements.txt')));

        if (options.pythonInstallationSettings.virtualEnv) {
          pythonPath = path.join(envPath, ((process.platform === 'win32') ? 'Scripts/python.EXE' : 'bin/python'));

          this.logger.debug('Creating virtual environment');
          await runCommand([pythonInstallation.path, '-m', 'venv', envPath], { architecture, timeout: 60e3 });

          this.logger.debug('Installing pip-tools');
          await runCommand([pythonPath, '-m', 'pip', 'install', 'pip-tools'], { architecture, timeout: (5 * 60e3) });

          this.logger.debug('Installing dependencies');
          await runCommand([pythonPath, '-m', 'piptools', 'compile'], { architecture, cwd: hostDirPath, timeout: 60e3 });
          await runCommand([pythonPath, '-m', 'piptools', 'sync'], { architecture, cwd: hostDirPath, timeout: (5 * 60e3) });
        }

        this.logger.debug('Initializing host configuration');

        let [confStdout, _] = await runCommand([pythonPath, '-m', 'pr1_server', '--data-dir', hostDirPath, '--initialize'], { architecture, timeout: 60e3 });
        conf = JSON.parse(confStdout) as ServerConfiguration;
      } catch (err: any) {
        util.logError(err, this.logger);

        await shell.trashItem(hostDirPath);

        return {
          ok: false,
          reason: 'other',
          message: err.message ?? 'Unknown error'
        };
      }

      this.logger.info(`Created host with identifier '${conf.identifier}'`);

      await this.setData({
        hostSettingsRecord: {
          ...this.data.hostSettingsRecord,
          [hostSettingsId]: {
            id: hostSettingsId,
            label: options.label,
            options: {
              type: 'local',
              architecture: options.pythonInstallationSettings.architecture,
              conf,
              dirPath: hostDirPath,
              identifier: conf.identifier,
              pythonPath
            }
          } satisfies HostSettings
        }
      });

      return {
        ok: true,
        hostSettingsId
      };
    });

    ipcMain.handle('hostSettings.delete', async (_event, { hostSettingsId }) => {
      let { [hostSettingsId]: deletedHostSettings, ...hostSettingsRecord } = this.data.hostSettingsRecord;
      await this.setData({ hostSettingsRecord });

      if (deletedHostSettings.options.type === 'local') {
        await shell.trashItem(deletedHostSettings.options.dirPath);
      }
    });

    ipcMain.handle('hostSettings.getHostCreatorContext', async (_event) => {
      // console.log(require('util').inspect(this.pythonInstallations, { colors: true, depth: Infinity }));

      return {
        computerName: util.getComputerName(),
        pythonInstallations: this.pythonInstallations
      };
    });

    ipcMain.handle('hostSettings.list', async (_event) => {
      return {
        defaultHostSettingsId: this.data.defaultHostSettingsId,
        hostSettingsRecord: this.data.hostSettingsRecord
      };
    });

    ipcMain.handle('hostSettings.revealLogsDirectory', async (_event, { hostSettingsId }) => {
      let logsDirPath = path.join(this.hostsLogsDirPath, hostSettingsId);
      await fs.mkdir(logsDirPath, { recursive: true });

      shell.showItemInFolder(logsDirPath);
    });

    ipcMain.handle('hostSettings.revealSettingsDirectory', async (_event, { hostSettingsId }) => {
      let hostSettings = this.data.hostSettingsRecord[hostSettingsId];

      assert(hostSettings.options.type === 'local');
      shell.showItemInFolder(hostSettings.options.dirPath);
    });

    ipcMain.handle('hostSettings.selectPythonInstallation', async (event) => {
      let result = await dialog.showOpenDialog(
        BrowserWindow.fromWebContents(event.sender)!,
        { buttonLabel: 'Select',
          filters: [
            ...(process.platform === 'win32'
              ? [{ name: 'Executables', extensions: ['exe'] }]
              : []),
            { name: 'All Files', extensions: ['*'] }
          ],
          properties: ['dontAddToRecent', 'noResolveAliases', 'openFile'] }
      );

      if (result.canceled) {
        return null;
      }

      let installationPath = result.filePaths[0];
      let info = await util.getPythonInstallationInfo(installationPath);

      if (!info) {
        dialog.showErrorBox('Invalid file', 'This file does not correspond to a valid Python installation.');
        return null;
      }

      return {
        id: installationPath,
        info,
        path: installationPath,
        leaf: false,
        symlink: false
      };
    });

    ipcMain.handle('hostSettings.setDefault', async (_event, { hostSettingsId }) => {
      await this.setData({ defaultHostSettingsId: hostSettingsId });
    });

    ipcMain.handle('hostSettings.queryRemoteHosts', async (_event) => {
      return (await searchForAdvertistedHosts())
        .map((info) => ({
          ...info,
          bridges: info.bridges.filter((bridge): bridge is BridgeTcp => (bridge.type === 'tcp'))
        }))
        .filter((info) => (info.bridges.length > 0))
        .filter((info) =>
          !Object.values(this.data.hostSettingsRecord).some((hostSettings) =>
            (hostSettings.options.identifier === info.identifier)
          )
        );
    });


    // Other

    ipcMain.on('hostSettings.launchHost', async (_event, { hostSettingsId }) => {
      this.launchHost(hostSettingsId);
    });


    // Draft management

    ipcMain.handle('drafts.create', async (event, contents) => {
      let result = await dialog.showSaveDialog(
        BrowserWindow.fromWebContents(event.sender)!,
        { filters: ProtocolFileFilters }
      );

      if (result.canceled) {
        return null;
      }

      let draftEntry = {
        id: crypto.randomUUID() as DraftEntryId,
        name: null,
        entryPath: result.filePath!
      };

      await fileManager.writeFile(draftEntry.entryPath, contents);

      await this.setData({
        drafts: { ...this.data.drafts, [draftEntry.id]: draftEntry }
      });

      return {
        id: draftEntry.id,
        entryPath: draftEntry.entryPath,
        name: draftEntry.name
      };
    });

    ipcMain.handle('drafts.delete', async (event, draftEntryId) => {
      let { [draftEntryId]: _, ...drafts } = this.data.drafts;
      await this.setData({ drafts });
    });

    ipcMain.handle('drafts.list', async () => {
      return Object.values(this.data.drafts).map<DraftSkeleton>((draftEntry) => ({
        id: draftEntry.id,
        entryPath: draftEntry.entryPath,
        name: draftEntry.name
      }));
    });

    ipcMain.handle('drafts.openFile', async (event, filePath) => {
      shell.openPath(filePath);
    });

    ipcMain.handle('drafts.query', async (event) => {
      let result = await dialog.showOpenDialog(
        BrowserWindow.fromWebContents(event.sender)!,
        { filters: ProtocolFileFilters,
          properties: ['openFile'] }
      );

      if (result.canceled) {
        return null;
      }

      let entryPath = result.filePaths[0];
      let draftEntry = Object.values(this.data.drafts).find((draftEntry) => (draftEntry.entryPath === entryPath));

      if (!draftEntry) {
        draftEntry = {
          id: crypto.randomUUID() as DraftEntryId,
          name: null,
          entryPath
        };

        await this.setData({
          drafts: { ...this.data.drafts, [draftEntry.id]: draftEntry }
        });
      }

      return {
        id: draftEntry.id,
        entryPath: draftEntry.entryPath,
        name: draftEntry.name
      };
    });

    ipcMain.handle('drafts.revealFile', async (event, filePath) => {
      shell.showItemInFolder(filePath);
    });

    ipcMain.handle('drafts.setName', async (event, draftEntryId, name) => {
      let draftEntry = this.data.drafts[draftEntryId];

      await this.setData({
        drafts: {
          ...this.data.drafts,
          [draftEntry.id]: {
            ...draftEntry,
            name
          }
        }
      });
    });

    let fileManager = new FileManager();
    this.disposables.add(fileManager);

    // @ts-expect-error
    ipcMain.handle('drafts.watch', async (event, filePath: string) => {
      return await fileManager.watchFile(filePath, event.sender);
    });

    ipcMain.handle('drafts.watchStop', async (event, filePath) => {
      await fileManager.unwatchFile(filePath, event.sender);
    });

    ipcMain.handle('drafts.write', async (event, filePath, contents) => {
      await fileManager.writeFile(filePath, contents);
    });


    // Stores

    ipcMain.handle('store.read', async (event, storeName, key) => {
      return this.data.stores[storeName]?.[key];
    });

    ipcMain.handle('store.readAll', async (event, storeName) => {
      return Object.entries(this.data.stores[storeName] ?? {});
    });

    ipcMain.handle('store.write', async (event, storeName, key, value) => {
      await this.setData({
        stores: {
          ...this.data.stores,
          [storeName]: {
            ...this.data.stores[storeName],
            [key]: value
          }
        }
      });
    });


    // Internal host

    ipcMain.handle('host.ready', async (_event, hostSettingsId) => {
      this.hostWindows[hostSettingsId].ready();
    });

    ipcMain.on('host.sendMessage', async (_event, hostSettingsId, message) => {
      this.hostWindows[hostSettingsId].sendMessage(message);
    });


    if (this.data.defaultHostSettingsId) {
      this.launchHost(this.data.defaultHostSettingsId);
    } else {
      this.createStartupWindow();
    }
  }


  launchHost(hostSettingsId: HostSettingsId) {
    this.logger.info(`Launching host settings with id '${hostSettingsId}'`);

    let existingWindow = this.hostWindows[hostSettingsId];

    if (existingWindow) {
      if (!existingWindow.closing) {
        this.startupWindow?.window.close();
        existingWindow.focus();
      }
    } else {
      let hostSettings = this.data.hostSettingsRecord[hostSettingsId];

      this.startupWindow?.window.close();
      this.createHostWindow(hostSettings);
    }
  }


  async loadData() {
    this.logger.info('Loading app data');

    await fs.mkdir(this.dataDirPath, { recursive: true });

    if (await fsExists(this.dataPath)) {
      this.logger.debug('Reading app data');

      let buffer = await fs.readFile(this.dataPath);
      let data = JSON.parse(buffer.toString());

      if (data.version !== CoreApplication.version) {
        this.logger.critical(`App version mismatch, found: ${data.version}, current: ${CoreApplication.version}`)
        dialog.showErrorBox('App data version mismatch', 'The app is outdated.');

        return;
      }

      this.data = data;
    } else {
      this.logger.debug('Creating app data');

      await this.setData({
        embeddedPythonInstallation: null,
        defaultHostSettingsId: null,
        drafts: {},
        hostSettingsRecord: {},
        stores: {},
        version: CoreApplication.version
      } satisfies AppData);
    }
  }

  async setData(data: Partial<AppData>) {
    this.data = { ...this.data, ...data };

    await this.dataLock.acquireWith(async () => {
      await fs.writeFile(this.dataPath, JSON.stringify(this.data));
    });
  }
}

async function main() {
  if (require('electron-squirrel-startup')) {
    electron.app.quit();
    return;
  }

  let core = new CoreApplication(electron.app);
  await core.initialize();
}


main().catch((err) => {
  console.error(err);
});
