"""Testes do ETL com dados sintéticos (rodam em segundos): python -m unittest discover -s tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import etl  # noqa: E402

OC_HEADER = ("id;data_inversa;dia_semana;horario;uf;br;km;municipio;causa_acidente;tipo_acidente;classificacao_acidente;fase_dia;"
             "sentido_via;condicao_metereologica;tipo_pista;tracado_via;uso_solo;pessoas;mortos;feridos_leves;feridos_graves;ilesos;"
             "ignorados;feridos;veiculos;latitude;longitude;regional;delegacia;uop")


def oc_row(id_, data, mortos=0, br="101", lat="-10,5", lon="-40,2", cls="Sem Vítimas"):
    return (f"{id_};{data};sexta-feira;18:30:00;BA;{br};12,5;SALVADOR;Falta de atenção;Colisão traseira;{cls};Pleno dia;Crescente;"
            f"Céu Claro;Simples;Reta;Sim;2;{mortos};0;0;2;0;0;2;{lat};{lon};SPRF-BA;DEL01;UOP01")


INF_NEW = ("Número do Auto;Data da Infração (DD/MM/AAAA);Hora Infração;UF Infração;BR Infração;Km Infração;Município;Sentido Trafego;"
           "Indicador de Abordagem;Assinatura do Auto;Indicador Veiculo Estrangeiro;UF Placa;Descrição Especie Veículo;Descrição Tipo Veículo;"
           "Descrição Marca Veículo;Descrição Modelo Veiculo;Código da Infração;Descrição Abreviada Infração;Enquadramento da Infração;"
           "Medição Infração;Medição Considerada;Excesso Verificado;Qtd Infrações")
INF_OLD = ("dat_infracao;tip_abordagem;ind_assinou_auto;ind_veiculo_estrangeiro;ind_sentido_trafego;uf_placa;uf_infracao;num_br_infracao;"
           "num_km_infracao;nom_municipio;descricao_abreviada;enquadramento;data_inicio_vigencia;data_fim_vigencia;med_realizada;"
           "med_considerada;exc_verificado;especie;nome_veiculo_marca;nom_modelo_veiculo")


class EtlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name) / "raw"
        self.out = Path(self.tmp.name) / "processed"
        self.raw.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text, enc="latin-1"):
        (self.raw / name).write_text(text, encoding=enc)

    def test_detect_kind_by_header_not_by_name(self):
        self.assertEqual(etl.detect_kind([etl.norm_header(c) for c in OC_HEADER.split(";")]), "ocorrencias")
        self.assertEqual(etl.detect_kind([etl.norm_header(c) for c in INF_NEW.split(";")]), "infracoes")
        self.assertEqual(etl.detect_kind([etl.norm_header(c) for c in INF_OLD.split(";")]), "infracoes")
        self.assertEqual(etl.detect_kind(["id", "pesid", "id_veiculo", "idade"]), "pessoas")
        self.assertEqual(etl.detect_kind(["id", "causa_acidente", "causa_principal", "ordem_tipo_acidente"]), "causas_tipos")
        self.assertIsNone(etl.detect_kind(["a", "b"]))

    def test_numbers_and_dates(self):
        s = pd.Series(["8e+05", "12,5", "x", None])
        self.assertEqual(list(etl.to_int(s)[:2]), [800000, 12])
        self.assertTrue(etl.to_num(s).iloc[2] != etl.to_num(s).iloc[2])  # NaN
        d = etl.parse_dates(pd.Series(["2026-07-19", "19/07/2026", "lixo"]))
        self.assertEqual(str(d.iloc[0].date()), "2026-07-19")
        self.assertEqual(str(d.iloc[1].date()), "2026-07-19")
        self.assertTrue(pd.isna(d.iloc[2]))

    def test_ocorrencias_cleaning_and_idempotence(self):
        rows = [oc_row("8e+05", "2026-01-10", mortos=1, cls="NA"), oc_row(2, "11/02/2026", br="0", lat="0", lon="0"), oc_row(2, "11/02/2026", br="0", lat="0", lon="0")]
        self.write("datatran2026.csv", OC_HEADER + "\n" + "\n".join(rows) + "\n", enc="utf-8")
        etl.run_etl(self.raw, self.out)
        df = etl.read_table("ocorrencias", processed=self.out)
        self.assertEqual(len(df), 2)  # duplicata removida
        self.assertIn(800000, df["id"].tolist())  # notação científica corrigida
        r = df[df["id"] == 800000].iloc[0]
        self.assertEqual(r["classificacao_acidente"], "Com Vítimas Fatais")  # derivada das contagens
        r2 = df[df["id"] == 2].iloc[0]
        self.assertTrue(pd.isna(r2["br"]) and pd.isna(r2["latitude"]))  # br=0 e (0,0) anulados
        self.assertEqual(r2["ano_mes"], "2026-02")
        m = etl.load_manifest(self.out)
        self.assertEqual(len(m["ingestions"]), 1)
        self.assertEqual(m["ingestions"][0]["tratamentos"]["ajuste:id_em_notacao_cientifica_convertido"], 1)
        etl.run_etl(self.raw, self.out)  # reexecução: nada muda
        self.assertEqual(len(etl.load_manifest(self.out)["ingestions"]), 1)
        self.assertEqual(len(etl.read_table("ocorrencias", processed=self.out)), 2)

    def test_new_year_is_appended_and_same_month_supersedes_with_archive(self):
        self.write("datatran2026.csv", OC_HEADER + "\n" + oc_row(1, "2026-01-10") + "\n")
        etl.run_etl(self.raw, self.out)
        self.write("datatran2025.csv", OC_HEADER + "\n" + oc_row(10, "2025-03-05") + "\n")
        etl.run_etl(self.raw, self.out)
        self.assertEqual(sorted(etl.read_table("ocorrencias", processed=self.out)["ano_mes"].astype(str)), ["2025-03", "2026-01"])
        # arquivo atualizado cobrindo janeiro/2026 substitui a partição anterior (que é arquivada)
        self.write("datatran2026_v2.csv", OC_HEADER + "\n" + oc_row(1, "2026-01-10", mortos=2) + "\n" + oc_row(3, "2026-01-12") + "\n")
        etl.run_etl(self.raw, self.out)
        df = etl.read_table("ocorrencias", processed=self.out)
        self.assertEqual(len(df[df["ano_mes"].astype(str) == "2026-01"]), 2)
        self.assertEqual(int(df[df["id"] == 1]["mortos"].iloc[0]), 2)
        self.assertTrue(list((self.out / "_superseded").rglob("*.csv.gz")))

    def test_infracoes_new_and_legacy_headers(self):
        new = INF_NEW + "\n" + ";".join(["abc1", "2026-07-19", "14", "RJ", "101", "100", "NITEROI", "C", "S", "N/I", "BR", "RJ", "PASSAGEIRO", "AUTOMOVEL",
                                         "FIAT", "UNO", "74550", "Transitar em velocidade superior à máxima em até 20%", "art. 218, I", "N/I", "92", "12", "1"]) + "\n"
        self.write("infracoes2026_07.csv", new)
        old = INF_OLD + "\n" + ";".join(["19/07/2015", "S", "", "N", "C", "RJ", "RJ", "101", "100", "NITEROI", "Transitar em velocidade superior à máxima em até 20%",
                                          "art. 218, I", "", "", "Radar", "80", "10", "PASSAGEIRO", "FIAT", "UNO"]) + "\n"
        self.write("infracoes2015.csv", old)
        etl.run_etl(self.raw, self.out)
        parts = list(etl.iter_table("infracoes", processed=self.out))
        df = pd.concat([p.astype({"ano_mes": "object"}) for p in parts])
        self.assertEqual(sorted(df["ano_mes"]), ["2015-07", "2026-07"])
        self.assertEqual(int(df["excesso_velocidade"].min()), 1)
        row = df[df["ano_mes"] == "2026-07"].iloc[0]
        self.assertEqual(row["limite_via_kmh"], 80.0)
        self.assertEqual(row["veiculo_estrangeiro"], 0)  # 'BR' = nacional
        self.assertEqual(row["grupo_infracao"], "Excesso de velocidade")

    def test_grupo_veiculo(self):
        self.assertEqual(etl.grupo_veiculo("Motocicleta"), "Motocicletas")
        self.assertEqual(etl.grupo_veiculo("Caminhão-trator"), "Caminhões e reboques")
        self.assertEqual(etl.grupo_veiculo("Automóvel"), "Automóvel e utilitários")
        self.assertEqual(etl.grupo_veiculo("Ônibus"), "Ônibus")
        self.assertEqual(etl.grupo_veiculo("Bicicleta"), "Bicicletas")

    def test_unrecognised_file_is_ignored(self):
        self.write("qualquer.csv", "a;b\n1;2\n")
        etl.run_etl(self.raw, self.out)
        self.assertEqual(etl.load_manifest(self.out)["ingestions"], [])


if __name__ == "__main__":
    unittest.main()
