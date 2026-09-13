const CHARTS_KEY = 'koolkid_tv_chart_layouts_v1';
const STUDIES_KEY = 'koolkid_tv_study_templates_v1';

type StoredChart = { id: string; name: string; symbol: string; resolution: string; timestamp: number; content: string };
type StoredStudy = { name: string; content: string };

function read<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) || '') as T; } catch { return fallback; }
}

function write(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value));
}

export function createTradingViewLocalStorageAdapter() {
  return {
    getAllCharts: async () => read<StoredChart[]>(CHARTS_KEY, []).map((row) => ({ id: row.id, name: row.name, symbol: row.symbol, resolution: row.resolution, timestamp: row.timestamp })),
    removeChart: async (id: string) => write(CHARTS_KEY, read<StoredChart[]>(CHARTS_KEY, []).filter((row) => row.id !== id)),
    saveChart: async (chart: Omit<StoredChart, 'id' | 'timestamp'> & { id?: string }) => {
      const rows = read<StoredChart[]>(CHARTS_KEY, []);
      const id = chart.id || crypto.randomUUID();
      const saved = { ...chart, id, timestamp: Date.now() } as StoredChart;
      const index = rows.findIndex((row) => row.id === id);
      if (index >= 0) rows[index] = saved; else rows.push(saved);
      write(CHARTS_KEY, rows);
      return id;
    },
    getChartContent: async (id: string) => read<StoredChart[]>(CHARTS_KEY, []).find((row) => row.id === id)?.content || '',
    getAllStudyTemplates: async () => read<StoredStudy[]>(STUDIES_KEY, []).map(({ name }) => ({ name })),
    removeStudyTemplate: async ({ name }: { name: string }) => write(STUDIES_KEY, read<StoredStudy[]>(STUDIES_KEY, []).filter((row) => row.name !== name)),
    saveStudyTemplate: async (template: StoredStudy) => {
      const rows = read<StoredStudy[]>(STUDIES_KEY, []).filter((row) => row.name !== template.name);
      rows.push(template); write(STUDIES_KEY, rows);
    },
    getStudyTemplateContent: async ({ name }: { name: string }) => read<StoredStudy[]>(STUDIES_KEY, []).find((row) => row.name === name)?.content || '',
    getAllDrawingTemplates: async () => [],
    removeDrawingTemplate: async () => undefined,
    saveDrawingTemplate: async () => undefined,
    loadDrawingTemplate: async () => null,
  };
}
