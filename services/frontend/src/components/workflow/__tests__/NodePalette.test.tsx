import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RiskLevel } from '@common/generated';
import type { NodeConfig } from '@common/generated';

const mockGetCatalog = jest.fn();
jest.mock('../../../lib/api/nodeApi', () => ({
  getCatalog: (...args: unknown[]) => mockGetCatalog(...args),
}));

import NodePalette, { PALETTE_MIME } from '../NodePalette';

const CATALOG: NodeConfig[] = [
  {
    node_id: 'id-http',
    node_type: 'http_request',
    name: 'HTTP 요청',
    category: 'integration',
    version: '1.0.0',
    input_schema: {},
    output_schema: {},
    parameter_schema: {},
    risk_level: RiskLevel.HIGH,
    required_connections: [],
    description: 'HTTP call',
    is_mvp: true,
  },
  {
    node_id: 'id-map',
    node_type: 'data_mapping',
    name: '데이터 매핑',
    category: 'transform',
    version: '1.0.0',
    input_schema: {},
    output_schema: {},
    parameter_schema: {},
    risk_level: RiskLevel.LOW,
    required_connections: [],
    description: 'Map fields',
    is_mvp: true,
  },
];

beforeEach(() => mockGetCatalog.mockReset());

describe('NodePalette', () => {
  it('fetches catalog and renders nodes grouped by category', async () => {
    mockGetCatalog.mockResolvedValueOnce(CATALOG);
    render(<NodePalette />);
    await waitFor(() => expect(screen.getByText('HTTP 요청')).toBeInTheDocument());
    expect(screen.getByText('데이터 매핑')).toBeInTheDocument();
    expect(screen.getByText('integration')).toBeInTheDocument();
    expect(screen.getByText('transform')).toBeInTheDocument();
  });

  it('uses provided catalog without fetching', async () => {
    render(<NodePalette catalog={CATALOG} />);
    await waitFor(() => expect(screen.getByText('HTTP 요청')).toBeInTheDocument());
    expect(mockGetCatalog).not.toHaveBeenCalled();
  });

  it('filters by search query', async () => {
    render(<NodePalette catalog={CATALOG} />);
    const input = screen.getByPlaceholderText(/검색/);
    await userEvent.type(input, 'http');
    expect(screen.getByText('HTTP 요청')).toBeInTheDocument();
    expect(screen.queryByText('데이터 매핑')).not.toBeInTheDocument();
  });

  it('sets palette drag payload on dragstart', async () => {
    render(<NodePalette catalog={CATALOG} />);
    await waitFor(() => screen.getByText('HTTP 요청'));
    const item = screen.getByTestId('palette-item-http_request');
    const setData = jest.fn();
    const dragEvent = new Event('dragstart', { bubbles: true }) as unknown as DragEvent;
    Object.defineProperty(dragEvent, 'dataTransfer', {
      value: { setData, effectAllowed: '' },
    });
    item.dispatchEvent(dragEvent);
    expect(setData).toHaveBeenCalledWith(
      PALETTE_MIME,
      expect.stringContaining('"node_type":"http_request"'),
    );
  });
});
