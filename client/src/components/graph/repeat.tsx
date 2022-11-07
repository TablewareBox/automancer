import * as React from 'react';
import { NodeContainer } from '../graph-editor';

import { BaseBlock, BaseMetrics, Renderer } from './spec';


export default {
  computeMetrics(block, options) {
    let childMetrics = options.computeMetrics(block.child);

    return {
      child: childMetrics,
      size: {
        width: childMetrics.size.width + 2,
        height: childMetrics.size.height + 3
      }
    };
  },
  render(block, metrics, position, options) {
    return (
      <>
        <NodeContainer
          cellSize={{ width: metrics.size.width, height: metrics.size.height }}
          position={position}
          settings={options.settings}
          title="Repeat" />
        {options.render(block.child, metrics.child, {
          x: position.x + 1,
          y: position.y + 2
        })}
      </>
    );
  }
} as Renderer<BaseBlock & {
  child: BaseBlock;
}, BaseMetrics & {
  child: BaseMetrics;
}>;
