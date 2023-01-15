import fs from 'fs/promises';
import path from 'path';

import type { HostSettings, HostSettingsId } from 'pr1';
import type { AppData } from 'pr1-app';
import { Scanner } from './scan';
import { SocketClient } from './socket-client';


export function getDesktopAppDataLocation(): string | null {
  switch (process.platform) {
    case 'darwin': return '/Users/simon/Library/Application Support/PR–1/App Data';
    case 'win32': return '...';
    default: return null;
  }
}


export const AppDataVersion = 1;

export async function getDesktopAppData() {
  let location = getDesktopAppDataLocation();

  if (!location) {
    return null;
  }

  let rawData;

  try {
    rawData = await fs.readFile(path.join(location, 'app.json'));
  } catch (err: any) {
    if (err.code === 'ENOENT') {
      return null;
    }

    throw err;
  }

  let data = JSON.parse(rawData.toString()) as AppData;

  if (data.version !== AppDataVersion) {
    return null;
  }

  return data;
}


export interface BridgeSocket {
  type: 'socket';
  options: {
    type: 'inet';
    hostname: string;
    port: number;
  } | {
    type: 'unix';
    path: string;
  };
}

export interface BridgeWebsocket {
  type: 'websocket';
  options: {
    hostname: string;
    port: number;
  };
}

export interface BridgeStdio {
  type: 'stdio';
  options: {};
}

export type Bridge = BridgeSocket | BridgeStdio | BridgeWebsocket;
export type BridgeRemote = BridgeSocket | BridgeWebsocket;


export type HostIdentifier = string;

export interface HostEnvironment {
  bridges: BridgeRemote[];
  identifier: HostIdentifier;
  hostSettings: HostSettings | null;
  label: string | null;
}

export type HostEnvironments = Record<HostIdentifier, HostEnvironment>;


export const UnixSocketDirPath = '/tmp/pr1';

export const SocketServiceType = '_prone._tcp.local';
export const WebsocketServiceType = '_prone._http._tcp.local';


export async function searchForHostEnvironments() {
  let environments: HostEnvironments = {};


  // Load known host settings

  let appData = await getDesktopAppData();

  for (let hostSettings of Object.values(appData?.hostSettings ?? {})) {
    if (hostSettings.options.type === 'local') {
      let identifier = hostSettings.options.identifier;

      environments[identifier] = {
        bridges: [],
        identifier,
        hostSettings,
        label: hostSettings.label
      };
    }
  }


  // Search for hosts advertisted over mDNS

  let services = await Scanner.getServices([
    SocketServiceType,
    WebsocketServiceType
  ]);

  for (let service of Object.values(services)) {
    let ipAddress = (service.address?.ipv4 || service.address?.ipv6);

    if (service.address && service.properties && ipAddress) {
      let identifier = service.properties['identifier'];

      if (!(identifier in environments)) {
        environments[identifier] = {
          bridges: [],
          identifier,
          hostSettings: null,
          label: service.properties['description']
        };
      }

      let environment = environments[identifier];

      if (service.types.includes(SocketServiceType)) {
        environment.bridges.push({
          type: 'socket',
          options: {
            type: 'inet',
            hostname: ipAddress,
            port: service.address.port
          }
        });
      }

      if (service.types.includes(WebsocketServiceType)) {
        environment.bridges.push({
          type: 'websocket',
          options: {
            hostname: ipAddress,
            port: service.address.port
          }
        });
      }
    }
  }


  // Search for UNIX sockets

  let socketFileNames;

  try {
    socketFileNames = await fs.readdir(UnixSocketDirPath);
  } catch (err: any) {
    if (err.code === 'ENOENT') {
      socketFileNames = [];
    }

    throw err;
  }

  for (let socketFileName of socketFileNames) {
    let match = /^(.*)\.sock$/g.exec(socketFileName);

    if (!match) {
      continue;
    }

    let identifier = match[1];

    let socketFilePath = path.join(UnixSocketDirPath, socketFileName);
    let isOpen = await SocketClient.test(socketFilePath);

    if (!isOpen) {
      continue;
    }

    if (!(identifier in environments)) {
      environments[identifier] = {
        bridges: [],
        hostSettings: null,
        identifier,
        label: null
      };
    }

    environments[identifier].bridges.push({
      type: 'socket',
      options: {
        type: 'unix',
        path: socketFilePath
      }
    });
  }

  return environments;
}

// searchForHostEnvironments().then((x) => {
//   console.log(require('util').inspect(x, { colors: true, depth: 1/0 }))
// });