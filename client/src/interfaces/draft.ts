import type { Diagnostic, Protocol } from 'pr1-shared';
import type { DraftCompletion, DraftFold, DraftHover, DraftMarker, DraftRelation, DraftRename, DraftSelection, DraftToken } from '../draft';
import type { DocumentPath } from '../app-backends/base';


export type HostDraftId = string;

export interface HostDraft {
  id: HostDraftId;
  documents: HostDraftDocument[];
}

export type HostDraftDocumentId = string;

export interface HostDraftDocument {
  id: HostDraftDocumentId;
  contents: string | null;
  path: string[] | null;
}

export interface HostDraftCompilerOptions {
  trusted: boolean;
}


export interface HostDraftCompilerResult {
  analysis: DraftLanguageAnalysis;
  missingDocumentPaths: DocumentPath[];
  protocol: Protocol | null;
  valid: boolean;
}


export interface DraftLanguageAnalysis {
  completions: DraftCompletion[];
  diagnostics: Diagnostic[];
  folds: DraftFold[];
  hovers: DraftHover[];
  markers: DraftMarker[];
  relations: DraftRelation[];
  renames: DraftRename[];
  selections: DraftSelection[];
  tokens: DraftToken[];
}
