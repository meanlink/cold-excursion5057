from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset
from src.services.business import metadata
from src.utils.serialization import checksum
import math, time
MAX_RECORDS=5000
def validate_rows(records):
    for index,row in enumerate(records):
        for c in metadata()['columns']:
            value=row.get(c['key'])
            if value is None or value=='': raise HTTPException(422, f'第 {index+1} 行缺少字段 {c["label"]}')
            if c['type']=='number':
                try:
                    if isinstance(value,bool) or not math.isfinite(float(value)): raise ValueError()
                    row[c['key']]=float(value)
                except (TypeError, ValueError, OverflowError): raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 必须为有限数值')
def merge_records(existing,incoming):
    # 相同记录只算一次；同路线同采样点或同路线同分钟的冲突明确拒绝；结果按分钟归位
    merged=list(existing)
    by_sample={(str(r.get('route')),str(r.get('sample'))):r for r in merged}
    by_minute={(str(r.get('route')),float(r['minute'])):r for r in merged}
    added=deduplicated=0
    for row in incoming:
        route,sample=str(row.get('route')),str(row.get('sample'))
        minute,temperature=float(row['minute']),float(row['temperature'])
        key=(route,sample)
        if key in by_sample:
            current=by_sample[key]
            if float(current['minute'])==minute and float(current['temperature'])==temperature:
                deduplicated+=1; continue
            raise HTTPException(409, f'记录冲突：{route} / {sample} 的分钟或温度与已有记录不一致')
        mkey=(route,minute)
        if mkey in by_minute:
            raise HTTPException(409, f'记录冲突：{route} 在 {minute:g} 分钟已存在采样点 {by_minute[mkey].get("sample")}')
        merged.append(row); by_sample[key]=row; by_minute[mkey]=row; added+=1
    merged.sort(key=lambda r:(str(r.get('route')),float(r['minute'])))
    return merged,added,deduplicated
def create(db, data):
    name=data.name.strip()
    if len(name)<2: raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name==name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    validate_rows(data.records)
    records,_,_=merge_records([],data.records)
    d=Dataset(name=name, source=data.source, records=records, checksum=checksum(records), created_at=time.time())
    db.add(d); db.flush()
    return d
def supplement(db, dataset_id, records):
    d=db.get(Dataset,dataset_id)
    if not d: raise HTTPException(404,'数据批次不存在')
    validate_rows(records)
    merged,added,deduplicated=merge_records(d.records,records)
    if len(merged)>MAX_RECORDS: raise HTTPException(422, f'合并后记录数超过 {MAX_RECORDS} 条上限')
    d.records=merged; d.checksum=checksum(merged); db.flush()
    return d,added,deduplicated
