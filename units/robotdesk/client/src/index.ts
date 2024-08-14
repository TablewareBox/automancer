/// <reference path="types.d.ts" />

import { Form, PanelDataList, PanelRoot, PanelSection, Plugin, createProcessBlockImpl, CreateFeaturesOptions, Features } from 'pr1';
import { PluginName, ProtocolBlockName } from 'pr1-shared';

import mainStyles from './index.css' assert { type: 'css' };


export const namespace = 'robotdesk';
export const styleSheets = [mainStyles];


export type DeviceId = string;

export interface Device {
  id: DeviceId;
  label: string;
}


export interface ExecutorState {
  devices: Record<DeviceId, Device>;
}

export interface ProcessLocationData {

}

export interface ProcessData {
  device: string
  x: number
  y: number
  z: number
  gripper_distance: number
}

export interface SegmentData {
  valves: Record<DeviceId, string | null>;
}

// export function createFeatures(options: CreateFeaturesOptions): Features {
//   let executor = options.host.state.executors[namespace] as ExecutorState;
//   let segmentData = options.segment.data[namespace] as SegmentData;
//   let previousSegmentData = options.protocol.segments[options.segmentIndex - 1]?.data[namespace] as SegmentData | undefined;

//   let features = [];

//   if (options.segment.processNamespace === namespace) {
//     features.push({
//       icon: '360',
//       label: 'Rotate valves'
//     });
//   }

//   features.push(...Object.values(executor.devices)
//     .filter((device) => {
//       let valve = segmentData.valves[device.id];
//       let previousValve = (previousSegmentData?.valves[device.id] ?? null);
//       return valve !== previousValve;
//     })
//     .map((device) => ({
//       icon: '360',
//       label: `Valve ${segmentData.valves[device.id]} (${device.label})`
//     }))
//   );

//   return features;
// }


// export default {
//   createFeatures,

//   blocks: {
//     ['_' as ProtocolBlockName]: createProcessBlockImpl<ProcessData, never>({
//       createFeatures
//     })
//   },
// }

export default {
  name: 'robotdesk',
  blocks: {
    ['_' as ProtocolBlockName]: createProcessBlockImpl({
      Component(props) {
        return (
          "Robot"
        );
      },
      createFeatures(data, location) {
        return [{
          icon: 'biotech',
          label: 'RobotDesk'
        }];
      }
    })
  }
}