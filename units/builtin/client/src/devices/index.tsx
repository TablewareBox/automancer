import { Chip, ChipTabComponentProps, Form } from 'pr1';
import { React } from 'pr1';


export const namespace = 'devices';


export interface BaseNode {
  id: string;
  connected: string;
  label: string | null;
}

export interface CollectionNode<T = BaseNode> extends BaseNode {
  nodes: Record<BaseNode['id'], T>;
}

export interface DeviceNode extends CollectionNode {
  model: string;
  owner: string;
}

export interface DataNode extends BaseNode {
  data: {
    type: 'boolean';
    targetValue: boolean | null;
    value: boolean | null;
  } | {
    type: 'select';
    options: { label: string; }[];
    targetValue: number | null;
    value: number | null;
  // } | {
  //   type: 'scalar';
  //   targetValue: number | null;
  //   value: number | null;
  } | {
    type: 'readScalar';
    value: number | null;
  };
}

export interface ExecutorState {
  root: CollectionNode<DeviceNode>;
}


export function getGeneralTabs() {
  return [
    {
      id: 'devices',
      label: 'Devices',
      icon: 'settings_input_hdmi',
      component: DevicesTab
    }
  ];
}


function DevicesTab(props: ChipTabComponentProps) {
  let executor = props.host.state.executors[namespace] as ExecutorState;

  React.useEffect(() => {
    props.host.backend.instruct({
      [namespace]: { type: 'register' }
    });
  }, []);

  // return (
  //   <main>
  //     <header className="header header--1">
  //       <h1>Devices</h1>
  //     </header>
  //     <pre>{JSON.stringify(executor, null, 2)}</pre>
  //   </main>
  // );

  return (
    <main>
      <header className="header header--1">
        <h1>Devices</h1>
      </header>

      {Object.values(executor.root.nodes).map((device) => (
        <React.Fragment key={device.id}>
          <header className="header header--2">
            <h2>{(device.label ? `${device.label} ` : '') + ` [${device.model}]`}</h2>
          </header>

          <p>Connected: {device.connected ? 'yes' : 'no'}</p>
          {/* <pre>{JSON.stringify(device, null, 2)}</pre> */}

          <Form.Form>
            {Object.values(device.nodes).map((node, nodeIndex) => {
              let label = (node.label ?? node.id);
              let data = (node as DataNode).data;

              if (data.type === 'boolean') {
                data = {
                  type: 'select',
                  options: [
                    { label: 'Off' },
                    { label: 'On' }
                  ],
                  targetValue: (data.targetValue !== null) ? (data.targetValue ? 1 : 0) : null,
                  value: (data.value !== null) ? (data.value ? 1 : 0) : null
                };
              }

              switch (data.type) {
                case 'readScalar': {
                  return (
                    <React.Fragment key={node.id}>{label}: {data.value ?? '–'}</React.Fragment>
                  );
                }

                case 'scalar': {
                  return (
                    <Form.TextField
                      label={label}
                      // onInput={(value) => {
                      //   props.host.backend.instruct({
                      //     [namespace]: {
                      //       type: 'setValue',
                      //       deviceId: device.id,
                      //       nodeIndex: nodeIndex,
                      //       value: parseFloat(value)
                      //     }
                      //   });
                      // }}
                      value={data.targetValue !== null ? data.targetValue.toString() : ''}
                      key={node.id} />
                  );
                }

                case 'select': {
                  let busy = (data.value !== data.targetValue);
                  let unknown = (data.value === null);

                  return (
                    <Form.Select
                      label={label + (node.connected ? '' : ' (disconnected)')}
                      onInput={(value) => {
                        props.host.backend.instruct({
                          [namespace]: {
                            type: 'setValue',
                            deviceId: device.id,
                            nodeIndex: nodeIndex,
                            value: (node.data.type === 'boolean') ? (value === 1) : value
                          }
                        });
                      }}
                      options={[
                        ...((unknown && !busy)
                          ? [{ id: -1, label: '–', disabled: true }]
                          : []),
                        ...data.options.map((option, index) => ({
                          id: index,
                          label: (busy && (data.targetValue === index) ? ((!unknown ? (data.options[data.value!].label + ' ') : '') + '→ ') : '') + option.label
                        }))
                      ]}
                      value={busy ? data.targetValue : (unknown ? -1 : data.value)}
                      key={node.id} />
                  );
                }
              }
            })}
          </Form.Form>
        </React.Fragment>
      ))}
    </main>
  );
}
