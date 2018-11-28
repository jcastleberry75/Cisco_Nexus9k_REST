import sys
import json
import xlrd
import pathlib
import requests
import logging
import threading
import urllib3
import subprocess

# USAGE: 
# 1. Scans a list of IPs to compare Vlans against a Master file of Vlan IDs.
# 2. Logs Master Vlan IDs not configured on the switch
# 3. Calls for IOS, CDP, and Interface status
# 4. Pipes all to JSON files


def logger_setup():
    log_format = '%(asctime)-s [%(levelname)-s] (%(threadName)-s)  %(message)s'
    logging.basicConfig(format=log_format,filename='nexus_9k_connector.log', level=logging.DEBUG)


logger_setup()
logging.info('#################### BEGIN NX-OS REST REQUESTS ####################')


def excel_reader(file):
    data = []
    filepath = ('./' + file)
    excel_data_file = pathlib.Path(filepath)
    if excel_data_file.exists():
        logging.info('Excel_File_Found')
        logging.info(str(excel_data_file) + '_'
                      + str(excel_data_file.exists()))
        pass
    else:
        logging.error('#####_No_Excel_Data_Sheet_Found_Exiting_#####')
        sys.exit()
    try:
        wb = xlrd.open_workbook(excel_data_file)
        sheet = wb.sheet_by_index(0)
        sheet.cell_value(0, 0)
        for row in range(sheet.nrows):
            r = str(sheet.cell_value(row, 0))
            data.append(r)
    except IOError:
        logging.error('An_error_occurred_trying_to_read_the_Excel_file.')
        sys.exit()

    return data


switch_list = excel_reader('CHANGE_ME.xlsx')
master_vlan_list = excel_reader('CHANGEME_vlans.xlsx')

logging.info('Switches to be polled: ' + str(switch_list))
logging.info('Master VLAN List: ' + str(master_vlan_list))


def switch_call():
    switchuser = 'CHANGEME'
    switchpassword = 'CHANGEME'
    show_ver = {}
    show_vlan = {}
    show_cdp_neighbor_detail = {}
    show_interface_status = {}

    def pinger(target):
        command_line_process = subprocess.Popen("ping /w 3 " + target, stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        process_output = command_line_process.communicate()
        logging.debug(process_output)

    def requestor():

        poplist = switch_list
        if poplist == []:
            pass
        else:
            address = poplist.pop()
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            url = 'https://' + address + '/ins'
            print(url)
            myheaders = {'content-type': 'application/json'}
            payload = {
                "ins_api": {
                    "version": "1.0",
                    "type": "cli_show",
                    "chunk": "0",
                    "sid": "1",
                    "input": "show version ;show vlan ;show cdp neighbor detail ;show interface status",
                    "output_format": "json"
                }
            }
            try:
                logging.info('Calling ' + url)
                response = requests.post(url, data=json.dumps(payload), headers=myheaders,
                                         auth=(switchuser, switchpassword), verify=False, timeout=(5, 10)).json()

                for k, v in response.items():
                    data = v
                    command_response_list = (data['outputs']['output'])
                    response_codes = [(key['input'], key['msg'], key['code'],) for key in command_response_list]
                    logging.info(response_codes)

                    for c in command_response_list:
                        # uncomment to dump to json files
                        if c['input'] == "show version":
                            show_ver[address] = (data['outputs']['output'][0]['body'])
                            # with open(str(ip) + '_show_ver.json', 'w') as outfile:
                            #     json.dump(show_ver[ip], outfile)
                        elif c['input'] == "show vlan":
                            show_vlan[address] = (data['outputs']['output'][1]['body']
                                                      ['TABLE_vlanbrief']['ROW_vlanbrief'])
                            # with open(str(address) + '_show_vlan.json', 'w') as outfile:
                            #     json.dump(show_vlan[address], outfile)

                        elif c['input'] == "show cdp neighbor detail":
                            show_cdp_neighbor_detail[address] = (data['outputs']['output'][2]['body'])
                            # with open(str(ip) + '_show_cdp_neigh.json', 'w') as outfile:
                            #     json.dump(show_cdp_neighbor_detail[ip], outfile)
                        elif c['input'] == "show interface status":
                            show_interface_status[address] = (data['outputs']['output'][3]['body'])
                            # with open(str(ip) + '_sh_int_status.json', 'w') as outfile:
                            #     json.dump(response, outfile)


            except Exception as e:
                print(e)
                logging.error(e)
                pinger(address)
                pass

            def vlan_check():
                sw_vlans = []
                missing_vlans = []
                vlans_ok = True
                for sw_name, vlan_data in show_vlan.items():
                    switch = sw_name
                    switch_vlans = vlan_data
                    for vlan_id_data in switch_vlans:
                        vlan_id = str(vlan_id_data['vlanshowbr-vlanid'])
                        sw_vlans.append(vlan_id)
                for vlan in master_vlan_list:
                    if vlan not in sw_vlans:
                        vlans_ok = False
                        missing_vlans.append(vlan)
                if vlans_ok is False:
                    master_vlan_ct = len(master_vlan_list)
                    missing_vlan_ct = len(missing_vlans)
                    missing_ct = master_vlan_ct - missing_vlan_ct
                    vlans_missing = str(missing_ct)
                    logging.warning(switch +
                                    '|VLANS_NOT_CONFIGURED| ' + str(missing_vlans) + '|' + vlans_missing)
                    with open('sw_missing_vlan_data.csv', 'a') as output:
                        output.write(switch +
                                     '|VLANS_NOT_CONFIGURED| ' + str(missing_vlans) + '|' + str(vlans_missing) + '\n')
            vlan_check()
    switch_count = len(switch_list)
    logging.info('Thread Count: ' + str(switch_count))
    threads = []
    for i in range(switch_count):
        t = threading.Thread(target=requestor)
        threads.append(t)
        t.start()


switch_call()