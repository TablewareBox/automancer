import { CreateFeaturesOptions, ProtocolState, util } from 'pr1';


export type NodePath = string[];

export interface BaseNode {
  id: string;
  icon: string | null;
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
    type: 'writableBoolean';
    currentValue: boolean | null;
    targetValue: boolean | null;
  } | {
    type: 'writableEnum';
    options: { label: string; }[];
    currentValue: number | null;
    targetValue: number | null;
  } | {
    type: 'readableScalar';
    value: number | null;
  } | {
    type: 'writableScalar';
    currentValue: number | null;
    targetValue: number | null;
  };
}

export interface ExecutorState {
  root: CollectionNode<DeviceNode>;
}

export interface UnitProtocolState {
  values: [NodePath, string][];
}


const namespace = 'devices';

function createStateFeatures(state: ProtocolState, descendantStates: ProtocolState[] | null, options: CreateFeaturesOptions) {
  let executor = options.host.state.executors[namespace] as ExecutorState;
  let unitStateData = state[namespace] as UnitProtocolState;

  let findNode = (node: BaseNode, path: NodePath): BaseNode =>
    path.length > 0
      ? findNode((node as CollectionNode).nodes[path[0]], path.slice(1))
      : node;

  return unitStateData.values.map(([path, value]) => {
    let node = findNode(executor.root, path);

    return {
      disabled: descendantStates?.some((descendantState) => {
        let unitDescendantState = descendantState[namespace] as UnitProtocolState;
        return unitDescendantState?.values.some(([descendantPath, _descendantValue]) => util.deepEqual(path, descendantPath));
      }),
      description: node.label ?? node.id,
      icon: node.icon ?? 'settings_input_hdmi',
      label: value
    };
  });
}


export default {
  createStateFeatures,
  namespace
}