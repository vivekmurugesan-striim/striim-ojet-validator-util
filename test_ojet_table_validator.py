import json, unittest
import ojet_table_validator as v

SQLPLUS = """
TABLE_NAME                               TABLE_OWNER               TO_CHAR(SCN)                   TIMESTAMP
---------------------------------------- ------------------------- ------------------------------ ---------
AADHAAR_MASKING_IMAGE_FILE               MFDSP_ARC                 11297544975005                 31-OCT-2026
IMAGE_DATA                               MFDSP_ARC                 11297544975157                 31-OCT-2026
"""

class T(unittest.TestCase):
    def test_list_a(self):
        self.assertEqual(v.parse_sqlplus_output(SQLPLUS),
                         {"MFDSP_ARC.AADHAAR_MASKING_IMAGE_FILE", "MFDSP_ARC.IMAGE_DATA"})
    def test_ora_error(self):
        with self.assertRaises(v.ValidationError):
            v.parse_sqlplus_output("ORA-01017: invalid username/password")
    def test_list_b_json(self):
        mon = json.dumps([{"Tables": "mfdsp_arc.image_data;MFDSP_ARC.OTHER", "name": "a.b"}])
        self.assertEqual(v.extract_tables_from_mon(mon),
                         {"MFDSP_ARC.IMAGE_DATA", "MFDSP_ARC.OTHER"})
    def test_list_b_text(self):
        self.assertEqual(v.extract_tables_from_mon("Tables: S.T1, S.T2"), {"S.T1", "S.T2"})
    def test_missing(self):
        a = {"S.T1", "S.T2"}
        self.assertEqual(v.find_missing(a, {"S.T1", "S.T3"}), ["S.T3"])
        self.assertEqual(v.find_missing(a, {"S.%"}), [])
        self.assertEqual(v.find_missing(a, {"X.%"}), ["X.%"])
    def test_input(self):
        with self.assertRaises(v.ValidationError):
            v.load_input('{"striim_username":"a"}')

if __name__ == "__main__":
    unittest.main()
