// اختبارات DataTable (DS) — التصيير، حالة الفراغ، الفرز بالنقر، وعرض render
// المخصّص للخلايا. لا بيانات وهميّة: نمرّر صفوفاً صريحة.
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { DataTable, type Column } from './table';

interface Field extends Record<string, unknown> {
  name: string;
  area: number;
}

const columns: Column<Field>[] = [
  { key: 'name', label: 'الحقل' },
  { key: 'area', label: 'المساحة', sortable: true, align: 'end' },
];

const rows: Field[] = [
  { name: 'حقل القمح', area: 12 },
  { name: 'حقل الذرة', area: 5 },
  { name: 'حقل البرسيم', area: 20 },
];

describe('DataTable', () => {
  it('يصيّر الرؤوس والصفوف', () => {
    render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.name} />);
    expect(screen.getByText('الحقل')).toBeInTheDocument();
    expect(screen.getByText('حقل القمح')).toBeInTheDocument();
    expect(screen.getAllByRole('row')).toHaveLength(rows.length + 1); // +رأس
  });

  it('يعرض حالة الفراغ حين لا صفوف', () => {
    render(<DataTable columns={columns} rows={[]} rowKey={() => 'x'} emptyTitle="لا حقول" />);
    expect(screen.getByText('لا حقول')).toBeInTheDocument();
    expect(screen.queryByRole('table')).toBeNull();
  });

  it('يفرز تصاعديّاً ثمّ تنازليّاً عند النقر على رأس قابل للفرز', () => {
    render(<DataTable columns={columns} rows={rows} rowKey={(r) => r.name} />);
    const sortBtn = screen.getByRole('button', { name: /المساحة/ });

    fireEvent.click(sortBtn); // asc → 5, 12, 20
    let bodyRows = screen.getAllByRole('row').slice(1);
    expect(within(bodyRows[0]).getByText('5')).toBeInTheDocument();
    expect(within(bodyRows[2]).getByText('20')).toBeInTheDocument();

    fireEvent.click(sortBtn); // desc → 20, 12, 5
    bodyRows = screen.getAllByRole('row').slice(1);
    expect(within(bodyRows[0]).getByText('20')).toBeInTheDocument();
    expect(within(bodyRows[2]).getByText('5')).toBeInTheDocument();
  });

  it('يستخدم render المخصّص للخلية', () => {
    const cols: Column<Field>[] = [
      { key: 'name', label: 'الحقل', render: (r) => <span>★ {r.name}</span> },
    ];
    render(<DataTable columns={cols} rows={[rows[0]]} rowKey={(r) => r.name} />);
    expect(screen.getByText('★ حقل القمح')).toBeInTheDocument();
  });
});
