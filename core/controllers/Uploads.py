import xml.etree.ElementTree as ET
import pandas as pd
import re
import json
import io
import os
import requests
import zipfile
import urllib3
import xlsxwriter
from django.shortcuts import render
from core.models import Empresas

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL_WS = "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline?wsdl"
HEADERS_WS = {
    "Content-Type": "text/xml;charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
}
MEMORIA_JSON_PATH = "core/static/js/conocimiento_contable.json"

def Uploadindex (request):
    return render(request, 'procesamiento/index.html')  
 

def cargar_memoria():
    """Carga la memoria JSON. Retorna un diccionario base si no existe."""
    if os.path.exists(MEMORIA_JSON_PATH):
        try:
            with open(MEMORIA_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            pass
    return {"empresas": {}}

def guardar_memoria(memoria):
    """Guarda la memoria JSON."""
    with open(MEMORIA_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(memoria, f, indent=4, ensure_ascii=False)

def procesar_archivos_entrada(lista_archivos):
    """
    Procesa una lista de archivos subidos (ej. Django UploadedFile).
    Retorna una lista de objetos io.BytesIO con el contenido de los XMLs encontrados.
    """
    xmls = []
    for f in lista_archivos:
        nombre = f.name.lower()
        if nombre.endswith('.xml'):
            f.seek(0)
            xmls.append(io.BytesIO(f.read()))
        elif nombre.endswith('.zip'):
            f.seek(0)
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    if n.lower().endswith('.xml') and not n.startswith('__MACOSX'):
                        xmls.append(io.BytesIO(z.read(n)))
    return xmls

def extraer_datos_robusto(xml_file, memoria):
    """
    Extrae los datos tributarios de un archivo XML y los cruza con la memoria para
    determinar su deducibilidad.
    """
    try:
        xml_file.seek(0)
        tree = ET.parse(xml_file)
        root = tree.getroot()
        xml_data = None
        
        for elem in root.iter():
            if 'comprobante' in elem.tag.lower() and elem.text and "<" in elem.text:
                xml_data = ET.fromstring(re.sub(r'<\?xml.*?\?>', '', elem.text).strip())
                break
        if xml_data is None:
            xml_data = root

        def buscar(tags):
            for t in tags:
                f = xml_data.find(f".//{t}")
                if f is not None and f.text:
                    return f.text.strip()
            return ""

        tag_lower = xml_data.tag.lower()
        tipo = "NC" if "notacredito" in tag_lower else "RET" if "retencion" in tag_lower else "LC" if "liquidacion" in tag_lower else "FC"
        
        razon_social = buscar(["razonSocial"]).upper()
        ruc_emisor = buscar(["ruc"])
        num_fact = f"{buscar(['estab']) or '000'}-{buscar(['ptoEmi']) or '000'}-{buscar(['secuencial']) or '000'}"
        fecha = buscar(["fechaEmision"])
        ruc_cli = buscar(["identificacionComprador", "identificacionSujetoRetenido"])
        nom_cli = buscar(["razonSocialComprador", "razonSocialSujetoRetenido"]).upper()

        len_id = len(ruc_cli)
        info_json = memoria.get("empresas", {}).get(razon_social)
        
        if len_id == 10:
            memo_final = "PERSONAL"
            detalle_final = info_json["DETALLE"] if info_json else "NO DEDUCIBLE"
        else:
            detalle_final = info_json["DETALLE"] if info_json else "OTROS"
            memo_final = info_json["MEMO"] if info_json else "PROFESIONAL"

        data = {
            "TIPO": tipo, "TIPO DE DOCUMENTO": tipo, "FECHA": fecha, "N. FACTURA": num_fact,
            "RUC": ruc_emisor, "CONTRIBUYENTE": ruc_cli, "NOMBRE": razon_social,
            "RUC CLIENTE": ruc_cli, "CLIENTE": nom_cli, "DETALLE": detalle_final, "MEMO": memo_final,
            "N AUTORIZACION": buscar(["numeroAutorizacion", "claveAcceso"])
        }
        
        if "/" in fecha:
            ms = {"01":"ENERO","02":"FEBRERO","03":"MARZO","04":"ABRIL","05":"MAYO","06":"JUNIO","07":"JULIO","08":"AGOSTO","09":"SEPTIEMBRE","10":"OCTUBRE","11":"NOVIEMBRE","12":"DICIEMBRE"}
            data["MES"] = ms.get(fecha.split('/')[1], "DESCONOCIDO")

        if tipo == "RET":
            r_renta, r_iva, b_renta, b_iva = 0.0, 0.0, 0.0, 0.0
            node = xml_data.find(".//numDocSustento")
            sus = node.text.replace('-','') if (node is not None and node.text) else ""
            if len(sus) >= 15:
                sus = f"{sus[0:3]}-{sus[3:6]}-{sus[6:]}"
            
            for item in (xml_data.findall(".//impuesto") + xml_data.findall(".//retencion")):
                try:
                    c = item.find("codigo").text
                    v = float(item.find("valorRetenido").text or 0)
                    b = float(item.find("baseImponible").text or 0)
                    if c == "1":
                        r_renta += v
                        b_renta += b
                    elif c == "2":
                        r_iva += v
                        b_iva += b
                except:
                    continue
                    
            data.update({
                "numfact": sus, "numreten": num_fact, "baserenta": b_renta, "rt_renta": r_renta,
                "baseiva": b_iva, "rt_iva": r_iva, "TOTAL RET": r_renta+r_iva, "SUSTENTO": sus, "fechaemi": fecha
            })
        else:
            m = -1 if tipo == "NC" else 1
            b0, b12, i12, ice, prop, no_obj, exento, otra_b, otro_i = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
            for imp in xml_data.findall(".//totalImpuesto"):
                try:
                    c = imp.find("codigo").text
                    cp = imp.find("codigoPorcentaje").text
                    b = float(imp.find("baseImponible").text or 0) * m
                    v = float(imp.find("valor").text or 0) * m
                    if c == "2":
                        if cp == "0": b0 += b
                        elif cp in ["2","3","4","8","10"]: b12 += b; i12 += v
                        elif cp == "6": no_obj += b
                        elif cp == "7": exento += b
                        else: otra_b += b; otro_i += v
                    elif c == "3":
                        ice += v
                except:
                    continue
            
            total_val = 0.0
            for t_tag in ["importeTotal", "total", "valorModificado"]:
                f = xml_data.find(f".//{t_tag}")
                if f is not None:
                    total_val = float(f.text) * m
                    break
            
            p_node = xml_data.find(".//propina")
            prop = float(p_node.text or 0) * m if p_node is not None else 0.0

            items = [d.find("descripcion").text for d in xml_data.findall(".//detalle") if d.find("descripcion") is not None]
            data.update({
                "OTRA BASE IVA": otra_b, "OTRO IVA": otro_i, "MONTO ICE": ice, "PROPINAS": prop,
                "EXENTO DE IVA": exento, "NO OBJ IVA": no_obj, "BASE. 0": b0, "BASE. 12 / 15": b12,
                "IVA.": i12, "TOTAL": total_val, "SUBDETALLE": " | ".join(items[:5])
            })
            
        return data
    except Exception as e:
        return None

def procesar_ventas_con_retenciones(lista):
    """Cruza la información de las facturas de venta con sus respectivas retenciones."""
    vts, rets = [], {}
    for d in lista:
        if d["TIPO"] == "FC":
            vts.append(d)
        elif d["TIPO"] == "RET" and d.get("SUSTENTO"):
            rets[d["SUSTENTO"]] = d
            
    res = []
    for v in vts:
        r = rets.get(v["N. FACTURA"], {})
        res.append({
            "MES": v.get("MES"), "FECHA": v["FECHA"], "N. FACTURA": v["N. FACTURA"],
            "RUC": v["RUC CLIENTE"], "CLIENTE": v["CLIENTE"], "DETALLE": "SERVICIOS",
            "MEMO": "PROFESIONAL", "MONTO REEMBOLS": 0.0,
            "BASE. 0": v.get("BASE. 0", 0), "BASE. 12 / 15": v.get("BASE. 12 / 15", 0),
            "IVA": v.get("IVA.", 0), "TOTAL": v.get("TOTAL", 0),
            "FECHA RET": r.get("fechaemi", ""), "N° RET": r.get("numreten", ""),
            "N° AUTORIZACIÓN": r.get("N AUTORIZACION", ""),
            "RET RENTA": r.get("rt_renta", 0), "RET IVA": r.get("rt_iva", 0),
            "ISD": 0.0, "TOTAL RET": r.get("TOTAL RET", 0)
        })
    return res

def generar_excel_multiexcel(data_compras=None, data_ventas_ret=None, data_sri_lista=None, sri_mode=None):
    """
    Genera un archivo Excel en memoria (BytesIO) y devuelve los bytes.
    Ideal para ser devuelto en un HttpResponse en Django.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        wb = writer.book
        f_azul = wb.add_format({'bold':True,'align':'center','border':1,'bg_color':'#002060','font_color':'white'})
        f_amar = wb.add_format({'bold':True,'align':'center','border':1,'bg_color':'#FFD966'})
        f_verd = wb.add_format({'bold':True,'align':'center','border':1,'bg_color':'#92D050'})
        f_gris = wb.add_format({'bold':True,'align':'center','border':1,'bg_color':'#F2F2F2'})
        f_num = wb.add_format({'num_format':'_-$ * #,##0.00_-','border':1})
        f_tot = wb.add_format({'bold':True,'num_format':'_-$ * #,##0.00_-','border':1,'bg_color':'#EFEFEF'})
        
        texto_pie = "&LGenerado por RAPIDITO AI&Rrapidito.ec"
        meses = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

        # === MODO SRI ===
        if sri_mode:
            df = pd.DataFrame(data_sri_lista)
            if sri_mode == "NC":
                cols = ["NOMBRE","RUC","N AUTORIZACION","FECHA","TIPO DE DOCUMENTO","N. FACTURA","MES","RUC CLIENTE","CLIENTE","PROPINAS","BASE. 0","NO OBJ IVA","BASE. 12 / 15","IVA.","TOTAL"]
                fmt_h = f_amar
                sh_nm = "NOTAS DE CREDITO"
            elif sri_mode == "RET":
                cols = ["ruc_recep", "nomrecep", "fechaemi", "razonsocial", "ruc_emisor", "numfact", "numreten", "baserenta", "rt_renta", "baseiva", "rt_iva", "numautori"]
                fmt_h = f_verd
                sh_nm = "RETENCIONES"
            else:
                cols = ["MES","FECHA","N. FACTURA","TIPO DE DOCUMENTO","RUC","CONTRIBUYENTE","NOMBRE","DETALLE","MEMO","OTRA BASE IVA","OTRO IVA","MONTO ICE","PROPINAS","EXENTO DE IVA","NO OBJ IVA","BASE. 0","BASE. 12 / 15","IVA.","TOTAL","SUBDETALLE"]
                fmt_h = f_azul
                sh_nm = "FACTURAS"
            
            for c in cols: 
                if c not in df.columns: df[c] = ""
            ws = wb.add_worksheet(sh_nm)
            ws.set_footer(texto_pie)
            for i, c in enumerate(cols): ws.write(0, i, c, fmt_h)
            for r, row in enumerate(df[cols].values, 1):
                for c, v in enumerate(row): 
                    ws.write(r, c, v, f_num if isinstance(v, (float,int)) else wb.add_format({'border':1}))
            ws.set_column(0, len(cols)-1, 15)

        # === MODO MANUAL (CON CÁLCULOS) ===
        else:
            if data_compras:
                df_c = pd.DataFrame(data_compras)
                orden_c = ["MES","FECHA","N. FACTURA","TIPO DE DOCUMENTO","RUC","CONTRIBUYENTE","NOMBRE","DETALLE","MEMO","OTRA BASE IVA","OTRO IVA","MONTO ICE","PROPINAS","EXENTO DE IVA","NO OBJ IVA","BASE. 0","BASE. 12 / 15","IVA.","TOTAL","SUBDETALLE"]
                for c in orden_c: 
                    if c not in df_c.columns: df_c[c] = ""
                ws_c = wb.add_worksheet('COMPRAS')
                ws_c.set_footer(texto_pie)
                for i, c in enumerate(orden_c): 
                    ws_c.write(0, i, c, f_amar if i in range(9, 15) else f_azul)
                for r, row in enumerate(df_c[orden_c].values, 1):
                    for c, v in enumerate(row): 
                        ws_c.write(r, c, v, f_num if isinstance(v, (float,int)) else wb.add_format({'border':1}))
                
                # TOTALES COMPRAS
                ft = len(df_c) + 1
                ws_c.write(ft, 0, "TOTAL", f_tot)
                for ci in range(9, 19):
                    l = xlsxwriter.utility.xl_col_to_name(ci)
                    ws_c.write_formula(ft, ci, f"=SUM({l}2:{l}{ft})", f_tot)

                # REPORTE ANUAL
                ws_ra = wb.add_worksheet('REPORTE ANUAL')
                ws_ra.set_footer(texto_pie)
                ws_ra.set_column('A:K', 14)
                ws_ra.merge_range('B1:B2', "Negocios y\nServicios", f_azul)
                cats = ["VIVIENDA","SALUD","EDUCACION","ALIMENTACION","VESTIMENTA","TURISMO","NO DEDUCIBLE","SERVICIOS BASICOS"]
                icos = ["🏠","❤️","🎓","🛒","🧢","✈️","🚫","💡"]
                for i, (ct, ic) in enumerate(zip(cats, icos)):
                    ws_ra.write(0, i+2, ic, f_azul)
                    ws_ra.write(1, i+2, ct.title(), f_azul)
                    
                ws_ra.merge_range('K1:K2', "Total Mes", f_azul)
                ws_ra.write('B3', "PROFESIONALES", f_gris)
                ws_ra.merge_range('C3:J3', "GASTOS PERSONALES", f_gris)
                
                cl_sum = ["P","Q","O","N","J","M"]
                for r, mes in enumerate(meses):
                    f_idx = r+4
                    ws_ra.write(r+3, 0, mes.title(), f_num)
                    # Suma Profesionales
                    f_pr = "+".join([f"SUMIFS('COMPRAS'!${l}:${l},'COMPRAS'!$A:$A,\"{mes}\",'COMPRAS'!$I:$I,\"PROFESIONAL\")" for l in cl_sum])
                    ws_ra.write_formula(r+3, 1, "="+f_pr, f_num)
                    # Suma por categorías
                    for cidx, ct in enumerate(cats):
                        f_ct = "+".join([f"SUMIFS('COMPRAS'!${l}:${l},'COMPRAS'!$A:$A,\"{mes}\",'COMPRAS'!$H:$H,\"{ct}\")" for l in cl_sum])
                        ws_ra.write_formula(r+3, cidx+2, "="+f_ct, f_num)
                    ws_ra.write_formula(r+3, 10, f"=SUM(B{f_idx}:J{f_idx})", f_num)
                    
                ws_ra.write(15, 0, "TOTAL", f_tot)
                for c in range(1, 11):
                    l = xlsxwriter.utility.xl_col_to_name(c)
                    ws_ra.write_formula(15, c, f"=SUM({l}4:{l}15)", f_tot)

            if data_ventas_ret:
                df_v = pd.DataFrame(data_ventas_ret)
                ord_v = ["MES","FECHA","N. FACTURA","RUC","CLIENTE","DETALLE","MEMO","MONTO REEMBOLS","BASE. 0","BASE. 12 / 15","IVA","TOTAL","FECHA RET","N° RET","N° AUTORIZACIÓN","RET RENTA","RET IVA","ISD","TOTAL RET"]
                for c in ord_v: 
                    if c not in df_v.columns: df_v[c] = ""
                ws_v = wb.add_worksheet('VENTAS')
                for i, c in enumerate(ord_v): 
                    ws_v.write(0, i, c, f_verd if i >= 12 else f_azul)
                for r, row in enumerate(df_v[ord_v].values, 1):
                    for c, v in enumerate(row): 
                        ws_v.write(r, c, v, f_num if isinstance(v, (float,int)) else wb.add_format({'border':1}))
                
                # PROYECCION	
                ws_p = wb.add_worksheet('PROYECCION')
                ws_p.set_column('A:M', 15)
                for i, h in enumerate(["VENTAS", "COMPRAS", "TOTAL"]): 
                    ws_p.write(i+2, 0, h, f_azul)
                for c, mes in enumerate(meses):
                    col = c + 1
                    l = xlsxwriter.utility.xl_col_to_name(col)
                    ws_p.write(1, col, mes, f_azul)
                    ws_p.write_formula(2, col, f"=SUMIFS(VENTAS!$I:$I,VENTAS!$A:$A,\"{mes}\") + SUMIFS(VENTAS!$J:$J,VENTAS!$A:$A,\"{mes}\")", f_num)
                    if data_compras:
                        f_cp = "+".join([f"SUMIFS('COMPRAS'!${x}:${x},'COMPRAS'!$A:$A,{l}$2,'COMPRAS'!$I:$I,\"PROFESIONAL\")" for x in cl_sum])
                        ws_p.write_formula(3, col, "="+f_cp, f_num)
                    ws_p.write_formula(4, col, f"={l}3-{l}4", f_tot)

    return output.getvalue()

def procesar_txt_sri(contenido_txt):
    """
    Extrae las claves de acceso de 49 dígitos de un archivo TXT del SRI.
    `contenido_txt` debe ser un string o bytes (se decodificará).
    """
    if isinstance(contenido_txt, bytes):
        try:
            contenido_txt = contenido_txt.decode("latin-1")
        except UnicodeDecodeError:
            contenido_txt = contenido_txt.decode("utf-8", errors="ignore")
    return list(dict.fromkeys(re.findall(r'\d{49}', contenido_txt)))

def descargar_xmls_sri(lista_claves, tipo_filtro, memoria):
    """
    Descarga los XMLs del SRI usando claves de acceso,
    y extrae los datos usando la memoria para clasificación.
    
    `tipo_filtro` puede ser "FC", "NC" o "RET".
    Devuelve un diccionario con:
        - "data": lista de diccionarios parseados.
        - "zip_content": bytes del archivo ZIP resultante.
    """
    lst = []
    zip_buf = io.BytesIO()
    
    with zipfile.ZipFile(zip_buf, "a", zipfile.ZIP_DEFLATED) as zf:
        for cl in lista_claves:
            try:
                payload = f'<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ec="http://ec.gob.sri.ws.autorizacion"><soapenv:Body><ec:autorizacionComprobante><claveAccesoComprobante>{cl}</claveAccesoComprobante></ec:autorizacionComprobante></soapenv:Body></soapenv:Envelope>'
                r = requests.post(URL_WS, data=payload, headers=HEADERS_WS, verify=False, timeout=10)
                if "<autorizaciones>" in r.text:
                    zf.writestr(f"{cl}.xml", r.text)
                    d = extraer_datos_robusto(io.BytesIO(r.content), memoria)
                    if d and (d["TIPO"] == tipo_filtro or (tipo_filtro=="FC" and d["TIPO"]=="LC")):
                        lst.append(d)
            except Exception:
                continue
                
    return {
        "data": lst,
        "zip_content": zip_buf.getvalue()
    }
