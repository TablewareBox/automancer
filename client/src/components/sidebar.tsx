import { OrdinaryId } from 'pr1-shared';
import { Component } from 'react';

import styles from '../../styles/components/sidebar.module.scss';

import { BaseUrl } from '../constants';
import type { Host } from '../host';
import { HostInfo } from '../interfaces/host';
import * as util from '../util';
import { ContextMenuArea } from './context-menu-area';


const CollapsedStorageKey = 'sidebarCollapsed';


export interface SidebarProps {
  host: Host | null;
  hostInfo: HostInfo;

  setStartup?: (() => void) | null;
}

export interface SidebarState {
  collapsed: boolean;
  manualCollapseControl: boolean;
}

export class Sidebar extends Component<SidebarProps, SidebarState> {
  private controller = new AbortController();

  constructor(props: SidebarProps) {
    super(props);

    let collapsed;
    let manualCollapseControl;

    try {
      collapsed = JSON.parse(window.sessionStorage[CollapsedStorageKey]);
      manualCollapseControl = true;
    } catch (_err) {
      collapsed = false;
      manualCollapseControl = false;
    }

    this.state = {
      collapsed,
      manualCollapseControl
    };
  }

  override componentDidMount() {
    const AUTO_COLLAPSE_LOWER_WIDTH = 1000;
    const AUTO_COLLAPSE_UPPER_WIDTH = 1200;

    let rect = document.body.getBoundingClientRect();

    let observer = new ResizeObserver((entries) => {
      let newRect = entries[0].contentRect;

      if ((newRect.width < AUTO_COLLAPSE_LOWER_WIDTH) && !this.state.collapsed && (!this.state.manualCollapseControl || (rect.width > AUTO_COLLAPSE_LOWER_WIDTH))) {
        window.sessionStorage[CollapsedStorageKey] = JSON.stringify(true);

        this.setState({
          collapsed: true,
          manualCollapseControl: false
        });
      }

      if ((newRect.width > AUTO_COLLAPSE_UPPER_WIDTH) && this.state.collapsed && (!this.state.manualCollapseControl || (rect.width < AUTO_COLLAPSE_UPPER_WIDTH))) {
        window.sessionStorage[CollapsedStorageKey] = JSON.stringify(false);

        this.setState({
          collapsed: false,
          manualCollapseControl: false
        });
      }

      rect = newRect;
    });

    observer.observe(document.body);

    this.controller.signal.addEventListener('abort', () => {
      observer.disconnect();
    });
  }

  override componentWillUnmount() {
    this.controller.abort();
  }

  override render() {
    let url = navigation.currentEntry.url;

    let pluginEntries = this.props.host?.plugins && Object.values(this.props.host.plugins)
      .flatMap((plugin) => (plugin.views ?? []).map((entry) => ({
        ...entry,
        id: `plugin.${entry.id}`,
        route: `/unit/${plugin.namespace}/${entry.id}`
      })));

    let groups: {
      id: OrdinaryId;
      entries: {
        id: OrdinaryId;
        label: string;
        icon: string;
        route: string | null;
        onClick?(): void;
      }[];
    }[] = this.props.host
      ? [
        { id: 'main',
          entries: [
            { id: 'experiments',
              label: 'Experiments',
              icon: 'science',
              route: '/experiments' },
            { id: 'draft',
              label: 'Protocols',
              icon: 'receipt_long',
              route: '/draft' },
            { id: 'settings',
              label: 'Settings',
              icon: 'settings',
              route: '/settings' }
        ] },
        ...(pluginEntries && (pluginEntries?.length > 0)
          ? [{ id: 'unit', entries: pluginEntries }]
          : []),
//         { id: 'last',
//           entries: [
//             { id: 'conf',
//               label: 'Settings',
//               icon: 'settings',
//               route: '/settings' },
// /*             { id: 'design',
//               label: 'Design',
//               icon: 'design_services',
//               route: '/design' }, */
//             ...(this.props.setStartup
//                 ? [{
//                   id: 'startup',
//                   label: 'Start menu',
//                   icon: 'home',
//                   route: null,
//                   onClick: () => void this.props.setStartup?.()
//                 }]
//                 : [])
//           ] }
      ]
      : [];

    return (
      <ContextMenuArea
        createMenu={(_event) => [
          { id: '_header', name: 'Sidebar', type: 'header' },
          ...groups.flatMap((group, groupIndex) => {
            return [
              ...group.entries.map((entry) => ({
                id: [group.id, entry.id],
                icon: entry.icon,
                name: entry.label,
                checked: true
              })),
              ...(groupIndex < (groups.length - 1)
                ? [{ id: ['_header', groupIndex], type: 'divider' as const }]
                : [])
            ];
          })
        ]}
        onSelect={() => {}}>
        <aside className={util.formatClass(styles.root, { [styles.rootCollapsed]: this.state.collapsed })}>
          <div className={styles.headerRoot}>
            {/* {(hostSettingsRecord.length > 0) && (
              <select className={styles.headerSelect} value={this.props.selectedHostSettingsId ?? ''} onChange={(event) => {
                this.props.onSelectHost(event.currentTarget.value || null);
              }}>
                {!this.props.host && <option value="">–</option>}
                {hostSettingsRecord.map((hostSettings) => (
                  <option key={hostSettings.id} value={hostSettings.id}>{hostSettings.label ?? hostSettings.id}</option>
                ))}
              </select>
            )} */}
            <div className={styles.headerValueRoot}>
              <img src={this.props.hostInfo.imageUrl!} className={styles.headerValueIcon} />
              <div className={styles.headerValueTitle}>{this.props.hostInfo.label}</div>
              {/* <div className={styles.headerValueSubtitle}>{this.props.hostInfo.description}</div> */}
              <div className={styles.headerValueExpand}>
                <span className="material-symbols-sharp">unfold_more</span>
              </div>
            </div>
          </div>
          <nav className={styles.navRoot}>
            {groups.map((group) => (
              <div className={styles.navGroup} key={group.id}>
                {group.entries.map((entry) => {
                  return (
                    <a
                      href={BaseUrl + (entry.route ?? '#')}
                      className={util.formatClass(styles.navEntryRoot, {
                        '_selected': url.startsWith(BaseUrl + entry.route)
                      })}
                      key={entry.id}
                      onClick={entry.onClick && ((event) => {
                        event.preventDefault();
                        entry.onClick!();
                      })}>
                      <div className={styles.navEntryIcon}>
                        <div className="material-symbols-sharp">{entry.icon}</div>
                      </div>
                      <div className={styles.navEntryLabel}>{entry.label}</div>
                    </a>
                  );
                })}
              </div>
            ))}
          </nav>
          <div className={styles.navRoot}>
            <div className={styles.navGroup}>
              <button type="button" className={util.formatClass(styles.navEntryRoot)} onClick={() => {
                let collapsed = !this.state.collapsed;
                window.sessionStorage[CollapsedStorageKey] = JSON.stringify(collapsed);
                this.setState({
                  collapsed,
                  manualCollapseControl: true
                });
              }}>
                <div className={styles.navEntryIcon}>
                  <div className="material-symbols-sharp">{this.state.collapsed ? 'keyboard_double_arrow_right' : 'keyboard_double_arrow_left'}</div>
                </div>
                {/* <div className={styles.navEntryLabel}>Collapse</div> */}
              </button>
            </div>
          </div>
        </aside>
      </ContextMenuArea>
    );
  }
}
