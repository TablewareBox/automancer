import type { HostSettings, HostSettingsId } from 'pr1';


export interface DraftEntry {
  id: string;
  lastModified: number;
  name: string;
  path: string;
}

export interface PythonInstallation {
  id: string;
  leaf: boolean;
  path: string;
  info: {
    architectures: string[] | null;
    isVirtualEnv: boolean;
    supportsVirtualEnv: boolean;
    version: [number, number, number];
  };
  symlink: boolean;
}

export interface AppData {
  defaultHostSettingsId: string | null;
  drafts: DraftEntry[];
  embeddedPythonInstallation: null;
  hostSettings: Record<HostSettingsId, HostSettings>;
  preferences: {};
  version: number;
}
