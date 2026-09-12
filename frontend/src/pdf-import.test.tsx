import {afterEach, expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import PDFImport from './pdf-import';
const mock=vi.hoisted(()=>vi.fn());
vi.mock('./financial-pdf',()=>({financialPDF:mock}));
afterEach(()=>{cleanup();vi.resetAllMocks();});
it('requires reconciliation and confirmation, and invalidates output on layout changes',async()=>{
 mock.mockResolvedValue({csv:'Paid\r\n10.00',rows:1,records:[{amount:'10.00'}]});
 const onPrepared=vi.fn();
 render(<PDFImport file={new File(['test'],'statement.pdf')} profile={{columns:{amount:'Paid'},delimiter:',',date_format:'%Y-%m-%d',allowed_values:{}}} onPrepared={onPrepared} />);
 fireEvent.click(screen.getByRole('button',{name:'Extract financial rows locally'}));
 const confirm=await screen.findByRole('button',{name:'Confirm extracted rows for import'});
 expect((confirm as HTMLButtonElement).disabled).toBe(true);
 fireEvent.change(screen.getByLabelText('Expected paid total for selected rows'),{target:{value:'11.00'}});
 expect((confirm as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(screen.getByLabelText('Expected paid total for selected rows'),{target:{value:'10.00'}});
  expect(screen.getByRole('button',{name:'Download financial-only CSV'})).toBeTruthy();
  fireEvent.click(confirm);expect(onPrepared).toHaveBeenLastCalledWith(expect.any(Blob));
 fireEvent.change(screen.getByLabelText('Table top (%)'),{target:{value:'25'}});
 expect(onPrepared).toHaveBeenLastCalledWith(null);
 expect(screen.queryByRole('button',{name:'Confirm extracted rows for import'})).toBeNull();
});

it('clears the prior expected total when a new extraction starts',async()=>{
 mock.mockResolvedValue({csv:'Paid\r\n10.00',rows:1,records:[{amount:'10.00'}]});
 const onPrepared=vi.fn();
 render(<PDFImport file={new File(['test'],'statement.pdf')} profile={{columns:{amount:'Paid'},delimiter:',',date_format:'%Y-%m-%d',allowed_values:{}}} onPrepared={onPrepared} />);
 fireEvent.click(screen.getByRole('button',{name:'Extract financial rows locally'}));
 await screen.findByRole('button',{name:'Confirm extracted rows for import'});
 fireEvent.change(screen.getByLabelText('Expected paid total for selected rows'),{target:{value:'10.00'}});
 expect((screen.getByRole('button',{name:'Confirm extracted rows for import'}) as HTMLButtonElement).disabled).toBe(false);
 fireEvent.click(screen.getByRole('button',{name:'Extract financial rows locally'}));
 await screen.findByRole('button',{name:'Confirm extracted rows for import'});
 const expected=screen.getByLabelText('Expected paid total for selected rows') as HTMLInputElement;
 expect(expected.value).toBe('');
  expect((screen.getByRole('button',{name:'Confirm extracted rows for import'}) as HTMLButtonElement).disabled).toBe(true);
});

it('downloads the reviewed financial-only CSV without uploading the PDF',async()=>{
 const previousCreate=(URL as unknown as {createObjectURL?: unknown}).createObjectURL;
 const previousRevoke=(URL as unknown as {revokeObjectURL?: unknown}).revokeObjectURL;
 const createObjectURL=vi.fn(()=> 'blob:financial');
 const revokeObjectURL=vi.fn();
 Object.defineProperty(URL,'createObjectURL',{configurable:true,writable:true,value:createObjectURL});
 Object.defineProperty(URL,'revokeObjectURL',{configurable:true,writable:true,value:revokeObjectURL});
 const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
 try {
  mock.mockResolvedValue({csv:'Paid\r\n10.00',rows:1,records:[{amount:'10.00'}]});
  render(<PDFImport file={new File(['test'],'statement.pdf')} profile={{columns:{amount:'Paid'},delimiter:',',date_format:'%Y-%m-%d',allowed_values:{}}} onPrepared={vi.fn()} />);
  fireEvent.click(screen.getByRole('button',{name:'Extract financial rows locally'}));
  await screen.findByRole('button',{name:'Download financial-only CSV'});
  fireEvent.click(screen.getByRole('button',{name:'Download financial-only CSV'}));
  expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
  expect(click).toHaveBeenCalled();
  const anchor=click.mock.instances[0] as unknown as HTMLAnchorElement;
  expect(anchor.download).toBe('statement-financial.csv');
  await waitFor(()=>expect(revokeObjectURL).toHaveBeenCalledWith('blob:financial'));
 } finally {
  click.mockRestore();
  if(previousCreate===undefined) delete (URL as unknown as {createObjectURL?: unknown}).createObjectURL;
  else Object.defineProperty(URL,'createObjectURL',{configurable:true,writable:true,value:previousCreate});
  if(previousRevoke===undefined) delete (URL as unknown as {revokeObjectURL?: unknown}).revokeObjectURL;
  else Object.defineProperty(URL,'revokeObjectURL',{configurable:true,writable:true,value:previousRevoke});
 }
});
