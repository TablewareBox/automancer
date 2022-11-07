import { Set as ImSet } from 'immutable';
import * as React from 'react';

import { Icon } from './icon';
import * as util from '../util';

import RepeatRenderer from './graph/repeat';
import SegmentRenderer from './graph/segment';
import SequenceRenderer from './graph/sequence';
import { BaseBlock, BaseMetrics, Coordinates, Renderers, Size } from './graph/spec';


const Services: Renderers = {
  repeat: RepeatRenderer,
  segment: SegmentRenderer,
  sequence: SequenceRenderer
};


export interface GraphEditorProps {

}

export interface GraphEditorState {
  nodes: NodeDef[];
  selectedNodeIds: ImSet<NodeId>;
  size: Size | null;
}

export class GraphEditor extends React.Component<GraphEditorProps, GraphEditorState> {
  action: {
    type: 'select';
    singleTargetId: NodeId | null;
    startPoint: {
      x: number;
      y: number;
    };
    targets: {
      id: NodeId;
      startPosition: {
        x: number;
        y: number;
      };
    }[];
  } | {
    type: 'move';
    startPoint: {
      x: number;
      y: number;
    };
    targets: {
      id: NodeId;
      startPosition: {
        x: number;
        y: number;
      };
    }[];
  } | null = null;

  mouseDown = false;
  refContainer = React.createRef<HTMLDivElement>();

  tree: any;

  constructor(props: GraphEditorProps) {
    super(props);

    let repeat = (child: any) => ({
      id: crypto.randomUUID(),
      type: 'repeat',
      child
    });

    let duplicate = (child: any) => ({
      id: crypto.randomUUID(),
      type: 'sequence',
      children: [child, child]
    });

    this.tree = {
      id: '0',
      type: 'sequence',
      children: [
        repeat(duplicate(repeat(duplicate({
          id: '5',
          type: 'segment',
          label: 'Delta',
          features: [
            { icon: 'hourglass_empty', label: '10 min' },
          ]
        })))),
        { id: '1',
          type: 'segment',
          label: 'Alpha',
          features: [
            { icon: 'hourglass_empty', label: '10 min' },
            { icon: 'air', label: 'Neutravidin' }
          ]
        },
        { id: '2',
          type: 'segment',
          label: 'Beta',
          features: [
            { icon: 'hourglass_empty', label: '10 min' },
            { icon: 'air', label: 'Neutravidin' }
          ]
        },
        { id: '3',
          type: 'segment',
          label: 'Gamma',
          features: [
            { icon: 'hourglass_empty', label: '20 min' },
            { icon: 'air', label: 'Alpha' },
            { icon: 'air', label: 'Bravo' },
            { icon: 'air', label: 'Charlie' }
          ]
        }
      ]
    };

    // this.tree = this.tree.children[0];

    this.state = {
      nodes: [],
      selectedNodeIds: ImSet(),
      size: null
    };
  }

  componentDidMount() {
    let container = this.refContainer.current!;
    let rect = container.getBoundingClientRect();

    this.setState({
      size: {
        width: rect.width,
        height: rect.height
      }
    });
  }

  render() {
    if (!this.state.size) {
      return <div className="geditor-root" ref={this.refContainer} />;
    }

    let styles = this.refContainer.current!.computedStyleMap();
    // console.log(Object.fromEntries(Array.from(styles)));
    let cellPixelSize = CSSNumericValue.parse(styles.get('--cell-size')!).value;
    let nodeHeaderHeight = CSSNumericValue.parse(styles.get('--node-header-height')!).value;
    let nodePadding = CSSNumericValue.parse(styles.get('--node-padding')!).value;
    let nodeBodyPaddingY = CSSNumericValue.parse(styles.get('--node-body-padding-y')!).value;

    let cellCountX = Math.floor(this.state.size.width / cellPixelSize);
    let cellCountY = Math.floor(this.state.size.height / cellPixelSize);

    let settings: Settings = {
      cellPixelSize,
      nodeBodyPaddingY,
      nodeHeaderHeight,
      nodePadding
    };


    let computeMetrics = (block: BaseBlock) => {
      return Services[block.type].computeMetrics(block, {
        computeMetrics,
        settings
      });
    };

    let render = (block: BaseBlock, metrics: BaseMetrics, position: Coordinates) => {
      return Services[block.type].render(block, metrics, position, { render, settings });
    };

    let treeMetrics = computeMetrics(this.tree);


    return (
      <div className="geditor-root" ref={this.refContainer}
        onMouseMove={(event) => {
          if (this.action?.type === 'select') {
            this.action = {
              type: 'move',
              startPoint: this.action.startPoint,
              targets: this.action.targets
            };
          }

          if (this.action?.type === 'move') {
            let dx = event.clientX - this.action.startPoint.x;
            let dy = event.clientY - this.action.startPoint.y;

            this.setState((state) => {
              if (!this.action) {
                return null;
              }

              return {
                nodes: state.nodes.map((node) => {
                  let target = this.action!.targets.find((target) => target.id === node.id);

                  if (!target) {
                    return node;
                  }

                  return {
                    ...node,
                    position: {
                      x: target.startPosition.x + dx / settings.cellSize,
                      y: target.startPosition.y + dy / settings.cellSize
                    }
                  };
                })
              };
            });
          }
        }}
        onMouseUp={(event) => {
          if ((this.action?.type === 'select') && (this.action.singleTargetId)) {
            this.setState({
              selectedNodeIds: ImSet.of(this.action.singleTargetId)
            });
          }

          if (this.action?.type === 'move') {
            let dx = event.clientX - this.action.startPoint.x;
            let dy = event.clientY - this.action.startPoint.y;

            let action = this.action;

            this.setState((state) => {
              return {
                nodes: state.nodes.map((node) => {
                  let target = action.targets.find((target) => target.id === node.id);

                  if (!target) {
                    return node;
                  }

                  return {
                    ...node,
                    position: {
                      x: target.startPosition.x + Math.round(dx / settings.cellSize),
                      y: target.startPosition.y + Math.round(dy / settings.cellSize)
                    }
                  };
                })
              };
            });
          }

          this.action = null;
        }}>
        <svg viewBox={`0 0 ${this.state.size.width} ${this.state.size.height}`} className="geditor-svg">
          <g>
            {new Array(cellCountX * cellCountY).fill(0).map((_, index) => {
              let x = index % cellCountX;
              let y = Math.floor(index / cellCountX);
              return <circle cx={x * cellPixelSize} cy={y * cellPixelSize} r="1.5" fill="#d8d8d8" key={index} />;
            })}
          </g>

          {render(this.tree, treeMetrics, { x: 1, y: 1 })}

          {/* <Link
            autoMove={this.action?.type !== 'move'}
            link={{
              start: {
                x: this.state.nodes[0].position.x + nodeWidth,
                y: this.state.nodes[0].position.y + 1
              },
              end: {
                x: this.state.nodes[2].position.x,
                y: this.state.nodes[2].position.y + 1
              }
            }}
            settings={settings} />
          <Link
            autoMove={this.action?.type !== 'move'}
            link={{
              start: {
                x: this.state.nodes[0].position.x + nodeWidth,
                y: this.state.nodes[0].position.y + 1
              },
              end: {
                x: this.state.nodes[1].position.x,
                y: this.state.nodes[1].position.y + 1
              }
            }}
            settings={settings} /> */}

          {/* <NodeContainer
            settings={settings}
            title={<>Repeat n times</>} /> */}

          {this.state.nodes.map((node) => (
            <Node
              autoMove={this.action?.type !== 'move'}
              node={node}
              onMouseDown={(event) => {
                event.preventDefault();

                // let selectedNodeIds = event.metaKey
                //   ? util.toggleSet(this.state.selectedNodeIds, node.id)
                //   : ImSet.of(node.id);

                // this.setState({ selectedNodeIds });

                let singleTargetId: NodeId | null = null;
                let selectedNodeIds;
                let targetNodeIds: ImSet<NodeId>;

                if (event.metaKey) {
                  selectedNodeIds = util.toggleSet(this.state.selectedNodeIds, node.id);
                  targetNodeIds = selectedNodeIds.has(node.id)
                    ? selectedNodeIds
                    : ImSet();
                } else {
                  selectedNodeIds = this.state.selectedNodeIds.has(node.id)
                    ? this.state.selectedNodeIds
                    : ImSet.of(node.id);
                  targetNodeIds = selectedNodeIds;

                  if (this.state.selectedNodeIds.has(node.id)) {
                    singleTargetId = node.id;
                  }
                }

                this.setState({ selectedNodeIds });

                // this.setState((state) => {
                //   if (event.metaKey) {
                //     return { selectedNodeIds: util.toggleSet(state.selectedNodeIds, node.id) };
                //   } else if ((state.selectedNodeIds.size > 1) || !state.selectedNodeIds.has(node.id)) {
                //     return { selectedNodeIds: ImSet([node.id]) };
                //   } else {
                //     return null; // return { selectedNodeIds: ImSet() };
                //   }
                // });

                if (!targetNodeIds.isEmpty()) {
                  this.action = {
                    type: 'select',
                    singleTargetId,
                    startPoint: {
                      x: event.clientX,
                      y: event.clientY
                    },
                    targets: targetNodeIds.toArray().map((nodeId) => {
                      let node = this.state.nodes.find((node) => node.id === nodeId)!;

                      return {
                        id: nodeId,
                        startPosition: node.position
                      };
                    })
                  };
                }
              }}
              selected={this.state.selectedNodeIds.has(node.id)}
              settings={settings}
              key={node.id} />
          ))}
        </svg>
      </div>
    );
  }
}


export interface Settings {
  cellPixelSize: number;
  nodeBodyPaddingY: number;
  nodeHeaderHeight: number;
  nodePadding: number;
}


type NodeId = string;

interface NodeDef {
  id: NodeId;
  title: string;
  features: {
    icon: string;
    label: string;
  }[];
  position: {
    x: number;
    y: number;
  };
}

export function Node(props: {
  autoMove: unknown;
  cellSize: Size;
  node: NodeDef;
  onMouseDown?(event: React.MouseEvent): void;
  selected: unknown;
  settings: Settings;
}) {
  let { node, settings } = props;

  return (
    <g
      className={util.formatClass('geditor-noderoot', { '_automove': props.autoMove })}
      transform={`translate(${settings.cellPixelSize * node.position.x} ${settings.cellPixelSize * node.position.y})`}>
      <foreignObject
        x="0"
        y="0"
        width={settings.cellPixelSize * props.cellSize.width}
        height={settings.cellPixelSize * props.cellSize.height}
        className="geditor-nodeobject">
        <div
          className={util.formatClass('geditor-node', { '_selected': props.selected })}
          onMouseDown={props.onMouseDown}>
          <div className="geditor-header">
            <div className="geditor-title">{node.title}</div>
          </div>
          <div className="geditor-body">
            {node.features.map((feature, index) => (
              <div className="geditor-feature" key={index}>
                <Icon name={feature.icon} />
                <div className="geditor-featurelabel">{feature.label}</div>
              </div>
            ))}
          </div>
        </div>
      </foreignObject>

      <circle
        cx={settings.nodePadding}
        cy={settings.nodePadding + settings.nodeHeaderHeight * 0.5}
        r="5"
        fill="#fff"
        stroke="#000"
        strokeWidth="2" />
      <circle
        cx={settings.cellPixelSize * props.cellSize.width - settings.nodePadding}
        cy={settings.nodePadding + settings.nodeHeaderHeight * 0.5}
        r="5"
        fill="#fff"
        stroke="#000"
        strokeWidth="2" />
    </g>
  );
}


interface LinkDef {
  start: { x: number; y: number; };
  end: { x: number; y: number; };
}

function Link(props: {
  autoMove: unknown;
  link: LinkDef;
  settings: Settings;
}) {
  let { link, settings } = props;

  let startX = settings.cellPixelSize * link.start.x - settings.nodePadding;
  let startY = settings.cellPixelSize * link.start.y;

  let endX = settings.cellPixelSize * link.end.x + settings.nodePadding;;
  let endY = settings.cellPixelSize * link.end.y;

  let d = `M${startX} ${startY}`;

  if (link.end.y !== link.start.y) {
    let dir = (link.start.y < link.end.y) ? 1 : -1;

    let midCellX = Math.round((link.start.x + link.end.x) * 0.5);
    let midX = settings.cellPixelSize * midCellX;

    let midStartX = settings.cellPixelSize * (midCellX - 1);
    let midEndX = settings.cellPixelSize * (midCellX + 1);

    let curveStartY = settings.cellPixelSize * (link.start.y + 1 * dir);
    let curveEndY = settings.cellPixelSize * (link.end.y - 1 * dir);

    d += `L${midStartX} ${startY}Q${midX} ${startY} ${midX} ${curveStartY}L${midX} ${curveEndY}Q${midX} ${endY} ${midEndX} ${endY}`;
  }

  d += `L${endX} ${endY}`;

  return <path d={d} className={util.formatClass('geditor-link', { '_automove': props.autoMove })} />
}


export function NodeContainer(props: {
  cellSize: Size;
  position: Coordinates;
  settings: Settings;
  title: React.ReactNode;
}) {
  let { settings } = props;

  return (
    <g className="geditor-group">
      <foreignObject
        x={settings.cellPixelSize * props.position.x}
        y={settings.cellPixelSize * props.position.y}
        width={settings.cellPixelSize * props.cellSize.width}
        height={settings.cellPixelSize * props.cellSize.height}
        className="geditor-groupobject">
          <div className="geditor-group">
            <div className="geditor-grouplabel">{props.title}</div>
          </div>
        </foreignObject>
    </g>
  );
}
