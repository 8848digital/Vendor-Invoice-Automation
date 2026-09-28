# TransBnk API Reference

Consolidated reference for the TransBnk (trusthub.in) API set shipped in `APIDocs.zip`. 117 PDFs in the zip reduced to **52 distinct documents** (many filenames were duplicate copies of the same combined PDF) covering **121 endpoints**.

**Common conventions across all endpoints:**
- Auth: header `x-api-key: <key>` (key issued by TransBnk after activation + IP whitelisting)
- Base URLs: UAT `https://sandbox-api.trusthub.in`, PROD `https://api.trusthub.in` (a few docs show `befisc.in` for UAT instead — inconsistency in the source docs, confirm before use)
- Method: POST JSON almost everywhere (`Content-Type: application/json; charset=utf-8`); exceptions are noted per-endpoint (a few GETs)
- Common error shapes: `{"message":"Forbidden"}` (bad/missing key or wrong method), `{"message":"Invalid request body"}`, IP-not-whitelisted, and upstream timeout
- Some newer docs (Beneficiary, Bank Account Validation, Bank Balance, BSA, DLC, Docuflow, Card Issuance, Virtual Gift Card) additionally require `x-client-id` / `x-username` / `x-client-password` headers and/or support an AES-256-ECB `encrypted_payload` request mode

---

## Aadhaar_OKYC_Resend_OTP_API

*Original zip filenames that were byte-identical duplicates of this doc:* Aadhaar_OKYC_Initiate_OTP_API, Aadhaar_OKYC_Submit_OTP_API


### Initiate OKYC
`POST` `/okyc-initiate-otp`

Triggers an OTP from UIDAI to the Aadhaar-linked mobile to begin paperless Aadhaar e-KYC.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| uid | yes | string | 12-digit Aadhaar number |
| uniqueId | yes | string | client reference for this request |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | string | 200 success / 400 / 500.. |
| model | object | transactionId, fwdp, codeVerifier, uidaiResponse{message,sessionActive,status} |
| msg | string | result message |

> fwdp/codeVerifier/transactionId from this response must be replayed into Submit OTP.


### Submit OTP
`POST` `/okyc-submit-otp`

Submits the UIDAI OTP to retrieve a presigned link to the Aadhaar XML zip plus demographic data.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| shareCode | yes | string | UIDAI share code, default 1234 |
| otp | yes | string |  |
| transactionId | yes | string |  |
| codeVerifier | yes | string |  |
| fwdp | yes | string |  |
| validateXml | yes | boolean |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | string |  |
| model | object | adharNumber, uniqueId, referenceId, maskedAdharNumber, name, gender, dob, careOf, passCode, link (zip URL, 60min), address{...}, image(base64), isXmlValid |
| msg | string |  |

> link is a presigned URL valid 60 minutes for the Aadhaar XML zip.


### Resend OTP
`POST` `/okyc-resend-otp`

Re-triggers the UIDAI OTP if not received; max 2 times after 60s each, only before Submit OTP is called.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| uid | yes | string |  |
| uniqueId | yes | string |  |
| transactionId | yes | string |  |
| fwdp | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | string |  |
| model | object | same shape as Initiate response |
| msg | string |  |

> Do not call after a failed Submit OTP — restart from Initiate instead.


---

## Account_Aggregator_Generate_URL_API

*Original zip filenames that were byte-identical duplicates of this doc:* Account_Aggregator_Retrieve_Report_API, Account_Aggregator_Status_Check_API


### Generate URL API
`POST` `/aa-generate-url`

Starts the Account Aggregator flow: verifies client credentials and returns a URL to redirect the end user to for consent/net-banking/PDF upload.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| client_ref_num | yes | string | max 50 chars, unique per txn |
| txn_completed_cburl | yes | string | webhook posted on completion |
| institution_id | no | string |  |
| mobile_num | no | string |  |
| aa_vendor | no | string |  |
| return_url | no | string | supports %s placeholders for txn_id/status |
| acceptance_policy | no | string |  |
| consent_request | no | array | fi_types, aa_fetch_type, fi_date_range, frequency, consent{mode,types,expiry} |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| url | string | URL to share/iframe with the customer |
| token | string |  |
| expires | string |  |
| txn_id | string |  |
| request_id | string |  |

> Errors returned as {status:'error', code, ...} with a documented code table (InvalidInstitution, DateRangeTooLarge, etc.).


### Status Check API
`POST` `/aa-status-check`

Polls the status of a previously started AA transaction (or use txn_completed_cburl webhook instead).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| request_id | yes | string | returned by Generate URL |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string | success/error |
| code | string | TxnStarted, TxnProcessing, StmtUploadComplete, ReportGenerated, UserCancelled, AccountBalanceMismatch, etc. |

> ReportGenerated means Retrieve Report API can now be called.


### Retrieve Report API
`POST` `/aa-retrieve-report`

Downloads the generated AA report (bank transactions/summary) for a completed transaction.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| txn_id | yes | string |  |
| report_type | no | string | json or xlsx |
| report_subtype | no | string | type1/type2/type3 for json; type3 for xlsx |

**Response fields**

| Field | Type | Description |
|---|---|---|
| (body) | file | raw JSON or XLSX report, content-type varies |

> txn_id can come from Status Check, Start Upload, or the completion webhook.


### Institution List API
`POST` `/bank-institution-list`

Lists banks/institutions supported by TransBnk for NetBanking or Statement flows, with their institution_id.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| type | no | string | 'NetBanking' or 'Statement' |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| data | array | [{id, name, insttype}] |

> Shared endpoint reused by Bank Statement Parsing docs too.


---

## Add_Beneficiary_API

*Original zip filenames that were byte-identical duplicates of this doc:* Beneficiary_Status_Enquiry_API


### Beneficiary API (Add/Modify/Deactivate)
`POST` `/beneficiary`

Registers, updates, or deactivates a payout beneficiary at a partner bank with checksum-based integrity and optional maker-checker.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| bankCode | yes | string | INDB/YESB/NSPB |
| customerId | yes | string |  |
| custRefNo | yes | string |  |
| checksum | yes | string | SHA-256 of the payload |
| beneficiary | yes | object | reqMode(A/M/D), txnType, benCode, benName, benIFSC, benAcctNo, benEmail, benMobile, remarks |
| callbackUrl | no | string |  |
| externalReferenceNumber | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| entityId | string |  |
| programId | number |  |
| custRefNo | string |  |
| status | string |  |
| message | string |  |

> Final activation status arrives via callbackUrl or the Beneficiary Status API, not synchronously.


### Beneficiary Status API
`POST` `/beneficiary-status`

Polls real-time activation status (Active/Inactive/Rejected/Failed/Validation-in-process) of a previously submitted beneficiary.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| custRefNo | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| entityId | string |  |
| programId | number |  |
| info | object | status(A/I/R/J/H), message, bankCode, benCode, benName, benIFSC, benAcctNo |
| custRefNo | string |  |

> Same payload shape is also POSTed to callbackUrl as a webhook.


---

## BBPS_BOU_Amount_Fetch_API

*Original zip filenames that were byte-identical duplicates of this doc:* BBPS_BOU_Payment_Confirmation_API


### BBPS BOU Payable Amount Fetch API
`POST` `/bbps-amount-fetch`

As a BBPS Biller Operating Unit, returns the payable EMI/overdue amount for a loan account so a bill-payment channel (BBPS UI etc) can display it.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| token | yes | string | static perpetual auth token |
| biller_id | yes | string |  |
| bbps_source | yes | string |  |
| loan_account_no | yes | string |  |
| mobile | no | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| ref_id | string |  |
| customer_name | string |  |
| emi_amt | number |  |
| overdue_amt | number |  |
| total_bill_amt | number |  |
| status_code | integer | 1 success / 2 failure |
| error_code | string | AB101-AB106 |

> Client here plays the biller role (loan servicer), not the payer — relevant only if TransBnk's client is itself a BBPS biller.


### BBPS BOU Payment Confirmation API
`POST` `/bbps-payment-confirmation`

Confirms to BBPS that a successful payment was received for a previously fetched bill.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| token | yes | string |  |
| ref_id | yes | string | from Amount Fetch response |
| loan_account_no | yes | string |  |
| txn_ref_no | yes | string |  |
| txn_amt | yes | number |  |
| status | yes | integer | must be 1 = successful |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status_code | integer |  |
| error_code | string | AB201-AB203 |

> Only successful payments should be posted here.


---

## BBPS_COU_Read_MDM_API

*Original zip filenames that were byte-identical duplicates of this doc:* BBPS_COU_Bill_Fetch_API, BBPS_COU_Bill_Payment_API, BBPS_COU_Complaint_Register_API, BBPS_COU_Download_MDM_API, BBPS_COU_Transaction_Status_API


### Bill Fetch API
`POST` `/bbps-cou-fetch-bill`

As a BBPS Customer Operating Unit, fetches bill details (amount, due date) for a biller/consumer combination before payment.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| chId | yes | integer |  |
| custDetails | yes | object | mobileNo, customerName, customerTags[] |
| agentDetails | yes | object | agentId, deviceTags[] |
| billDetails | yes | object | billerId, customerParams[] |

**Response fields**

| Field | Type | Description |
|---|---|---|
| respCode | string |  |
| status | string | SUCCESS/FAILURE |
| response | object | refId, approvalRefNum, billerResponse{customerName,amount,dueDate,...}, billTags |

> For fetch-mandatory billers, the returned refId must be reused in the Bill Payment call.


### Bill Payment API
`POST` `/bbps-cou-payment-bill`

Submits a bill payment for a fetched (or fetch-optional) biller with payment mode, amount and channel details.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| chId | yes | integer |  |
| refId | conditional | string |  |
| clientRequestId | yes | string |  |
| agentDetails | yes | object |  |
| amountDetails | yes | object | amount, currency, custConvFee, amountTags |
| billDetails | yes | object |  |
| custDetails | yes | object |  |
| paymentDetails | yes | object | paymentInfo, paymentMode, quickPay, splitPay, offusPay |
| bbpsPGResponse | yes | object | txRefNo, txnDateTime |

**Response fields**

| Field | Type | Description |
|---|---|---|
| respCode | string |  |
| status | string |  |
| response | object | refId, approvalRefNum, txnReferenceId, or complianceReason on failure |


### Transaction Status Check API
`POST` `/bbps-cou-txt-status`

Looks up the status of a BBPS payment by txnReferenceId and/or npciTxnReferenceId.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| billerId | yes | string |  |
| txnReferenceId | conditional | string |  |
| npciTxnReferenceId | conditional | string |  |
| xchangeId | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| respCode | string |  |
| status | string |  |
| response | object | apiResponseCode, billDetails, responseReason, txnReferenceId, xchangeId, or the literal string 'Transaction not Found' |


### Complaint Register API (4 sub-flows)
`POST` `/bbps-cou-complain-register`

Registers a transaction complaint, checks a transaction, fetches transaction history, or checks complaint status — differentiated by msgType/complainReq shape.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| msgType | yes | string |  |
| xchangeId | yes | string |  |
| complainReq | yes | object | varies: agentId/complaintType/mobile/description/disposition/txnReferenceId (register); txnReferenceId/complaintType (check txn); mobile/fromDate/toDate (history); complaintId (status check) |

**Response fields**

| Field | Type | Description |
|---|---|---|
| respCode | string |  |
| status | string |  |
| response | object | head.referenceId, txnStatusComplainResp{msgId,complaintId,complaintStatus,responseCode,txnList,custDetails} |

> One physical endpoint serving 4 logical operations distinguished by request shape.


### Read MDM API
`GET` `/bbps-cou-read-mdm`

Returns the legacy-format BBPS biller master data (one biller's config) as plain text.

**Response fields**

| Field | Type | Description |
|---|---|---|
| (body) | string | escaped JSON text with head + biller[] (payment modes, channels, fees, customerParams) |

> Only documented GET endpoint besides bs-retrieve-report and electricity-operator-code.


### Download MDM API
`POST` `/bbps-cou-download-mdm`

Downloads the full or date-filtered BBPS biller master-data file (new downloadable format).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| filterName | yes | string | 'date' or 'all' |
| filterValue | yes | string | yyyy-MM-dd date, or 'mdm' |

**Response fields**

| Field | Type | Description |
|---|---|---|
| (body) | file | downloadable BillerMDM_<date>.txt |

> filterName='all' returns the entire (very large) dataset — download rather than inline-parse.


---

## BSA_Upload_API

*Original zip filenames that were byte-identical duplicates of this doc:* BSA_Analysis_API, BSA_Check_Status_API, BSA_Create_Session_API, BSA_Retrieve_Report_API


### Bank Statement Create Session API
`POST` `/bs-create-session`

Opens a FinEye analysis session for a borrower + document type, given consent, ahead of uploading bank statement PDFs.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| borrowerId | yes | string |  |
| documentId | yes | string | e.g. '01' for bank statement |
| consent | yes | string | must be 'Y' |
| consent_text | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| api_category | string |  |
| message | string |  |
| result | object | session_id, expired_at |
| status | string | OKRES on success |
| txn_id | string |  |

> This is the 'FinEye' Financial Analysis Suite, a second, newer bank-statement-analysis product distinct from bank-stmt-2/bs-analysis naming aside.


### Bank Statement Upload API
`POST` `/bs-upload`

Uploads a base64 bank-statement PDF against a session created by bs-create-session.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| session_id | yes | string |  |
| file | yes | string | base64 PDF |
| pdf_file_password_b16 | no | string |  |
| overdraft | no | string |  |
| consent | yes | string |  |
| consent_text | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| message | string |  |
| session_id | string |  |
| status | string |  |
| txn_id | string |  |

> Multiple documents can be uploaded to the same session_id before calling Analysis.


### Bank Statement Analysis API
`POST` `/bs-analysis`

Kicks off analysis of all documents uploaded under a session_id.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| session_id | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| message | string |  |
| session_id | string |  |
| status | string |  |
| txn_id | string |  |

> Asynchronous — poll Check Status next.


### Bank Statement Check Status API
`POST` `/bs-check-status`

Polls processing status for a session's documents/reports.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| session_id | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| message | string | e.g. 'Report Generated Successfully' |
| status | string |  |


### Bank Statement Retrieve Report API
`GET` `/bs-retrieve-report`

Fetches presigned XLSX/JSON report links for a completed session.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| (session context via header/session) | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result | object | excel(url), json(url) |
| session_id | string |  |
| status | string |  |

> Presigned S3 URLs expire (X-Amz-Expires ~1800s in the sample).


---

## Bank_Account_Validation_API

*Original zip filenames that were byte-identical duplicates of this doc:* Bank_Account_Validation_API (1)


### Bank Account Validation API
`POST` `/bank-validateacct`

Verifies bank/UPI account ownership via IMPS penny-drop, penny-less, UPI, or reverse-VPA methods, returning nameAtBank and a fuzzy match score.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| requestId | yes | string |  |
| txnType | yes | string | ANY/IMPS/UPI/REVERSE/REVERSE_INTENT/IMPS_PD/IMPS_PL |
| custName | no | string |  |
| custIfsc | conditional | string | required for ANY/IMPS/UPI |
| custAcctNo | conditional | string |  |
| custVpa | conditional | string | required for REVERSE/REVERSE_INTENT |
| custMobileNo | no | string |  |
| callbackUrl | conditional | string | required for REVERSE/REVERSE_INTENT |

**Response fields**

| Field | Type | Description |
|---|---|---|
| statusCode | string | TB000 success, TBxxx error table |
| status | string |  |
| acValidationStatus | string | ACCOUNT_VALID/INVALID/BLOCKED/CLOSED/DORMANT etc |
| nameAtBank | string |  |
| fuzzyLogicScore | string | 0-100 name match |
| utr | string |  |
| qrUrlString | string | REVERSE_INTENT only |

> Also supports an AES-256-ECB encrypted_payload variant. Beneficiary-facing analogue of Beneficiary API but stateless/synchronous for non-reverse flows.


### Bank Account Validation Status API
`POST` `/bank-validateacct-status`

Retrieves the real-time processing status of a previously submitted validation request.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| origRequestId | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| statusCode | string |  |
| status | string |  |
| acValidationStatus | string |  |
| nameAtBank | string |  |
| fuzzyLogicScore | string |  |

> Same response shape family as the validation API itself.


### Bank Account Validation Callback API
`POST (inbound to client)` `(client-hosted, via callbackUrl)`

TBX pushes REVERSE/REVERSE_INTENT validation results to the client's own endpoint instead of the client polling Status API.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| (posted by TBX) | n/a | object | same shape as the validation response |

**Response fields**

| Field | Type | Description |
|---|---|---|
| (client returns 2xx) | n/a |  |

> Only fires for REVERSE / REVERSE_INTENT txnTypes when callbackUrl was supplied.


---

## Bank_Balance_API


### Bank Balance API
`POST` `/bank-balance`

Fetches real-time available/unclear balance for a bank account via TransBnk's bank integrations.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| bankCode | yes | string |  |
| entityId | yes | string |  |
| programId | yes | string |  |
| customerId | conditional | string | required for some banks, see bank table |
| userId | conditional | string |  |
| accountNumber | yes | string |  |
| customerRequestId | no | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| customerRequestId | string |  |
| status | string |  |
| message | string |  |
| data | object | balanceAmount, availabeBalance, unclearBalance, balanceDateTime |

> Field requirements (customerId/userId/tokenNumber) vary per bankCode — a 20-bank table is in the doc.


---

## Bank_Institution_List_API

*Original zip filenames that were byte-identical duplicates of this doc:* Bank_Statement_Parsing_Cancel_Request_API, Bank_Statement_Parsing_Complete_Upload_API, Bank_Statement_Parsing_Fetch_Report_API, Bank_Statement_Parsing_Start_Upload_API, Bank_Statement_Parsing_Status_Check_API


### Start Upload API
`POST` `/stmt-start-upload`

Begins a bank-statement-PDF-parsing transaction; verifies client credentials and returns an upload URL/token/request_id.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| client_ref_num | yes | string |  |
| txn_completed_cburl | yes | string |  |
| institution_id | yes | string |  |
| start_month/end_month | no | string |  |
| acceptance_policy | no | string |  |
| relaxation_days | no | string |  |
| employer_name | no | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| url | string | URL for the Upload Statement API |
| token | string |  |
| expires | string |  |
| txn_id | string |  |
| request_id | string |  |

> 5-step flow: Start Upload -> Upload Statement -> Complete Upload -> Status Check -> Retrieve Report; Cancel Request can abort at any stage.


### Upload Statement API
`POST` `(URL returned by Start Upload)`

Uploads one bank-statement PDF (or a presigned S3 file_url) against the transaction started by Start Upload.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| token | yes | string |  |
| file | conditional | string | base64 PDF; mutually exclusive with file_url |
| file_password_b16 | no | string |  |
| request_id | yes | string |  |
| file_url | conditional | string | presigned S3 PDF URL |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | string | StmtUploaded or an error code |
| msg | string |  |
| accounts | array | account_pattern, statement_end_date |

> No signature/auth-token needed for this call; a large error-code table covers password/scanned/multi-account failures.


### Complete Upload API
`POST` `/stmt-complete-upload`

Finalizes the upload phase and starts TransBnk's processing of the uploaded statements.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| request_id | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| code | string | OperationSuccess or error |
| msg | string |  |

> After this, poll Status Check or wait for txn_completed_cburl.


### Status Check API
`POST` `/stmt-status`

Checks processing status of the statement-parsing transaction (TxnStarted through ReportGenerated).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| request_id | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| request_id | string |  |
| txn_status | array | [{code, status, msg, txn_id}] |

> ReportGenerated unlocks Retrieve Report API.


### Retrieve Report API
`POST` `/stmt-fetch-report`

Downloads the parsed bank-statement report (json or xlsx).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| txn_id | yes | string |  |
| report_type | no | string |  |
| report_subtype | no | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| (body) | file | raw JSON or XLSX |

> Same report_type/subtype semantics as the AA Retrieve Report API.


### Cancel Request API
`POST` `/stmt-cancel-request`

Cancels an in-flight statement-parsing transaction at any stage after Start Upload.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| request_id | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| code | string |  |
| msg | string |  |


### Institution List API
`POST` `/bank-institution-list`

Lists banks supported for NetBanking or Statement upload flows.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| type | no | string | NetBanking or Statement |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| data | array | [{id, name, insttype}] |

> Identical endpoint to the one in the Account Aggregator doc.


---

## Bank_Payout_API

*Original zip filenames that were byte-identical duplicates of this doc:* Bulk_Payout_API, Payout_Resend_OTP_API, Payout_Status_Enquiry_API, Payout_Submit_OTP_API


### Bank Payout API
`POST` `/bank-payout`

Initiates an IMPS/NEFT/RTGS/IFT payout from a client-controlled bank account to a beneficiary (by account or benCode), optionally OTP-gated.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| bankCode | yes | string |  |
| customerId | yes | string |  |
| custTxnRefNo | yes | string |  |
| externalReferenceNumber | yes | string |  |
| debitAcctNo | yes | string |  |
| callbackUrl | no | string |  |
| payment | yes | object | txnType, amount, valueDate, benCode/benName/benIFSC/benAcctNo, benEmail, benMobile, description, remark1-3 |

**Response fields**

| Field | Type | Description |
|---|---|---|
| custTxnRefNo | string |  |
| status | string |  |
| message | string | 'OTP required' means call Submit OTP |
| utrNo | string | present for IMPS |

> If MFA is enabled on the program, response message is 'OTP required' and Submit OTP must be called to complete the payout.


### Payout Status Enquiry API
`POST` `/bank-payout-status`

Fetches the current status of a previously submitted payout.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| custTxnRefNo | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| custTxnRefNo | string |  |
| entityId | string |  |
| programId | string |  |
| info | object | status(large enum: PENDING/PROCESSED/REJECTED/RETURN/...), message, amount, utrNo, paymentDate |

> Same schema is POSTed to callbackUrl as a webhook.


### Payout Submit OTP
`POST` `/bank-payout-submitotp`

Submits the OTP required to authorize an MFA-gated payout.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| custTxnRefNo | yes | string |  |
| otp_value | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| custTxnRefNo | string |  |
| status | string |  |
| message | string |  |


### Payout Resend OTP
`POST` `/bank-payout-resendotp`

Requests resending of the payout-authorization OTP using the configured method.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| custTxnRefNo | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| custTxnRefNo | string |  |
| status | string |  |
| message | string |  |


### Bulk Payout API
`POST` `/bulk-payout`

Submits many payout instructions in one call for asynchronous batch processing.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| bankCode | yes | string |  |
| fileName | yes | string |  |
| typeOfPayout | yes | string |  |
| customerId | yes | string |  |
| debitAcctNo | yes | string |  |
| payout | yes | array | per-row custTxnRefNo, txnType, amount, benName, benIfsc, benAccountNo, description |

**Response fields**

| Field | Type | Description |
|---|---|---|
| message | string |  |
| data | string | 'Success' when the file is queued |

> Fire-and-forget; per-row results are not in this response — use Payout Status Enquiry per custTxnRefNo.


---

## Bank_Statement_API


### Bank Integration Service Statement API
`POST` `/bank-stmt`

Fetches raw transaction statement lines for a bank account over a date range (max 30 days per call, up to 6 months back) via TransBnk's bank integrations.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| customerRequestId | no | string |  |
| customerId | conditional | string |  |
| bankCode | yes | string |  |
| accountNumber | yes | string |  |
| fromDateTime | yes | string |  |
| toDateTime | yes | string |  |
| moreDataFlag | conditional | string | SURY bank only |

**Response fields**

| Field | Type | Description |
|---|---|---|
| customerRequestId | string |  |
| status | string |  |
| message | string |  |
| data | array | per-txn: transactionId, transactionDate, valueDate, transactionType(DR/CR), remarks, transactionReferenceNumber, transactionMode, transactionAmount, runningBalance |

> Different endpoint from Bank Balance/Bank Statement Analysis — this is the raw ledger fetch. Error codes BIS001-BIS009 documented.


---

## Bank_Statement_Analysis_API


### BSA Creation API
`POST` `/bank-stmt-2`

Submits a base64-encoded bank-statement PDF for automated cash-flow/income analysis (income assessment, EMI detection, fraud flags).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| tracking_id | yes | string | client-generated UUID |
| file | yes | string | base64 PDF |
| file_name | yes | string |  |
| file_password | no | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| data | array |  |
| metadata | array |  |
| status | string |  |
| message | string |  |
| success | boolean |  |

> This is the TBX 'BSA v1' family distinct from the newer FinEye bs-create-session/bs-upload/bs-analysis flow.


### BSA Status Enquiry API
`POST` `/bank-status`

Polls status and retrieves the analysis outputs (KPIs, cashflow, risk score) once processing completes.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| tracking_id | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| tracking_id | string |  |
| status | string | INITIATED/COMPLETED/FAILED/ERRORED/FETCH_ERRORED/PURGED/INITIATION_FAILED |
| xlsx_docs_url | string |  |
| json_docs_url | string |  |
| analyzed_json | object | analytics + score{transactionScore, area, tranche} |


---

## CIBIL_API


### CIBIL Report API
`POST` `/cibil-report`

Fetches a CIBIL credit report for an individual given demographic details and explicit data-sharing consent.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| CustomerInfo | yes | object | Name{Forename,Surname}, IdentificationNumber{IdentifierName,Id}, Address{...}, EmailID, DateOfBirth, PhoneNumber{Number}, Gender |
| LegalCopyStatus | yes | string | 'Accept' |
| UserConsentForDataSharing | yes | boolean |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| message | string |  |
| cibilData | object | GetCustomerAssetsResponse -> Asset{Status,CreationDate,ExpirationDate,TrueLinkCreditReport,...} |
| htmlUrl | string | secure one-time viewable credit report URL |

> This is the credit-bureau/risk-stage API mentioned in the requirement's 'Credit Bureau Reports' line item.


---

## CIN_Verification_API


### CIN Validation
`POST` `/cin-validation`

Retrieves MCA company master data, charges, and director/signatory details for a given 21-character CIN.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| cin | yes | string |  |
| client_ref_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result | object | data.company_master_data{cin,company_llp_name,roc_code,registration_number,company_category,authorised_capital,paid_up_capital,date_of_incorporation,registered_address,company_status,...}, data.charges[], data.directors_signatory_details[] |
| http_response_code | integer |  |
| result_code | integer | 101 valid, 103 invalid CIN |

> This is 'CIN-Based Company Profile' from the requirement; directors_signatory_details.din_pan gives director DIN/PAN, overlapping with 'MCA Director DIN Profile'.


### GSTIN Validation
`POST` `/gstin-validation`

Validates a 15-char GSTIN and returns basic taxpayer details, recent return-filing status, and registered goods/services (HSN/SAC).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| gstin | yes | string |  |
| client_ref_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result.taxpayerDetails | object | gstin,tradeNam,lgnm,ctb,sts(Active/Cancelled),dty,rgdt,cxdt,nba[],pradr.adr,ekycVFlag,adhrVFlag,stj,ctj |
| result.taxpayerReturnDetails | object | filingStatus[] (fy,taxp,mof,dof,rtntype,arn,status) |
| result.goods_service | object | bzgddtls[](gdes,hsncd), bzsdtls[](sdes,saccd) |

> This is the 'basic' GSTIN validator (no OTP/consent) — the requirement's 'GSTIN Active Status Validator' / 'GST Taxpayer Status – Lite' map here, and goods_service.bzgddtls covers 'HSN Code Lookup from GSTIN'.


### Advanced GSTIN Validation
`POST` `/gstin-advancedvalidation`

Superset of GSTIN Validation adding annual turnover slab, gross income, all business places, e-invoice mandate flag, and directors/members.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| gstin | yes | string |  |
| client_ref_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result.taxpayerDetails | object | adds gti,gtiFY,aggreTurnOver,aggreTurnOverFY,einvoiceStatus,mandatedeInvoice,mbr[] over the basic API |
| result.taxpayerReturnDetails | object |  |
| result.goods_service | object |  |
| result.business_places | object | pradr, adadr[] (all registered addresses) |

> Maps to 'GSTIN Deep Profile Validation' in the requirement.


### PAN to GSTIN Search
`POST` `/pan2gstin-search`

Lists all GSTIN(s) linked to a PAN, each with active/inactive status and state, optionally filtered by state.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| pan | yes | string |  |
| client_ref_num | yes | string |  |
| state | no | string |  |
| state_code | no | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result.count | string |  |
| result.gstinResList | array | [{gstin, authStatus, stateCd, state}] |

> This is the real 'PAN to GST Registration Mapper' from the requirement; the file literally named PAN_to_GSTIN_Search_API.pdf in the zip was a duplicate copy of the unrelated OTP-based GST Fitness Report doc, not this endpoint.


---

## CKYC_Search_API

*Original zip filenames that were byte-identical duplicates of this doc:* CKYC_Download_API


### Simple CKYC Search API
`POST` `/ckyc-search-2`

Looks up an individual/entity's CKYC ID and basic KYC details (name, father's name, photo) using any government ID.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| identifier | yes | string |  |
| identifier_type | yes | string | PASSPORT/VOTER_ID/PAN/DL/PROOF_OF_AADHAAR/NGREGA/NPR/CKYC_ID/CIN/RC |
| client_ref_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result_code | string |  |
| result | object | status(VALID/INVALID), name, fathers_name, age, kyc_date, photo(base64), ckyc_id |


### Simple CKYC Download API
`POST` `/ckyc-download-2`

Retrieves the full CKYC record (identity, address, images, document list) for a CKYC ID using an authentication factor.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| auth_factor_type | yes | string | DOB / PIN_YOB / MOBILE |
| auth_factor | yes | string |  |
| ckyc_id | yes | string |  |
| client_ref_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result_code | integer |  |
| result | object | personal_details{...}, identity_details{identity[]}, related_person_details, image_details{image[]} |
| status | string |  |

> result_code 108 means the user's application was rejected.


---

## Card_Create_API

*Original zip filenames that were byte-identical duplicates of this doc:* Card_Creation_Status_API, Customer_OTP_Generation_API, Customer_Registration_API, Full_KYC_URL_API, GPR_Card_Load_API, Load_Money_Status_API


### Customer OTP Generation API
`POST` `/customer-otp`

Sends an OTP to a customer's mobile as the first step of prepaid-card customer onboarding.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mobile | yes | string | 10-digit, pattern [0-9]{10} |

**Response fields**

| Field | Type | Description |
|---|---|---|
| message | string | 'OTP sent successfully' |

> Part of the Prepaid Card Issuance suite: OTP -> Register -> Full KYC -> Card Create -> Card Status -> GPR Load -> Load Status. Requires x-client-id/x-username/x-client-password headers in addition to x-api-key.


### Customer Registration API
`POST` `/customer-register`

Registers the customer with minimum KYC using the OTP from the previous step; returns a sender_tag used in all subsequent calls.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| name | yes | string |  |
| mobile | yes | string |  |
| email | yes | string |  |
| documentType | yes | string | AADHAR_NUMBER/DRIVING_LICENCE/PASSPORT_NUMBER/VOTER_ID |
| documentValue | yes | string |  |
| dateOfBirth | no | string |  |
| otp | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | object | code(2000=success,5000=failure), message |
| result | object | sender_tag(UUID, must be saved), message |


### Full KYC URL API
`POST` `/full-kyc-url`

Returns a time-limited redirect URL for the customer to complete Aadhaar e-KYC and PAN/Form60 verification.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| senderId | yes | string | the sender_tag UUID |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | object |  |
| result | object | expire_on, kyc_required, url, taxation_required |

> If both kyc_required and taxation_required are false, no redirect is needed — customer already fully KYC'd.


### Card Create API
`POST` `/card-create`

Creates a virtual GPR (reloadable) or Gift Card for a registered customer; asynchronous, poll status next.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| senderTag | yes | string |  |
| cardFormFactor | yes | string | only VIRTUAL supported |
| cardType | yes | string | GPR or GC |
| amount | yes | string | '0.00' for GPR; ₹100-₹10000 for GC |
| context | no | object |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | object |  |
| result | object | reference_id, is_otp_required, message, card_id, status(SUBMITTED/APPROVED/REJECTED/SUCCESS/NONE) |


### Card Creation Status API
`POST` `/card-creation-status`

Polls the outcome of a card-create request; card_id is populated only once status=SUCCESS.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| referenceId | yes | string |  |
| senderTag | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | object |  |
| result | object | reference_id, is_otp_required, message, card_id(UUID once issued), status(SUCCESS/SUBMITTED/FAILED) |


### GPR Card Load API
`POST` `/card-gpr-load`

Loads funds onto an already-issued GPR prepaid card.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| cardId | yes | string |  |
| amount | yes | string | ≥₹100; higher after full KYC |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | object |  |
| result | number | numeric load reference id, pass as referenceId to Load Money Status |


### Load Money Status API
`POST` `/card-load-money-status`

Checks the outcome of a GPR fund-load transaction.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| referenceId | yes | string | numeric id from GPR Card Load, passed as string |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | object |  |
| result | object | txn_id, message, status(SUCCESS/FAILED/PENDING) |


---

## DLC_Creation_API

*Original zip filenames that were byte-identical duplicates of this doc:* DLC_Creation_Status_Enquiry_API, DLC_Credit_List_API


### DLC Creation API
`POST` `/dlc-create`

Creates one or more Digital Ledger Codes (virtual payer-specific reference codes) tied to a bank account, for automated credit reconciliation.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| batchRefNo | yes | string |  |
| bankCode | yes | string | e.g. IDFB |
| accountNo | yes | string |  |
| callbackUrl | no | string |  |
| DLCRequests | yes | array | [{dLC, moreInfo[{label,value}]}] |

**Response fields**

| Field | Type | Description |
|---|---|---|
| batchRefNo | string |  |
| status | string |  |
| message | string |  |

> Not really a KYC/onboarding API — used for ongoing collections reconciliation once a vendor's bank account is already onboarded.


### DLC Creation Status Enquiry API
`POST` `/dlc-create-status`

Checks per-DLC creation status for a batch.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| batchRefNo | yes | string |  |
| entityId | yes | string |  |
| programId | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| info | array | [{status, message, DLC}] |


### DLC Credit List API
`POST` `/dlc-credits-list`

Lists bank credits (remitter, UTR, amount) received against a customer's DLCs within a date range, for reconciliation/reporting.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| customerCode | yes | string |  |
| fromDate | yes | string |  |
| toDate | yes | string |  |
| entityId | yes | string |  |
| programId | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| data | array | [{alertRefNo, amount, bankCreditDate, utrNo, remitterName, remitterAccountNumber, remittingBankName, remitterBankIfsc, DLC, DLCparts}] |


---

## DL_Advanced_API


### Driving License (Advance) Check API
`POST` `/dl-advance`

Verifies a driving license number + DOB and returns holder details, addresses, vehicle-category endorsements, and validity windows.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| dl_no | yes | string |  |
| DOB | yes | string | DD-MM-YYYY |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | integer | 1 success, 2 no record |
| result | object | user_address[], user_blood_group, dl_number, user_dob, expiry_date, issued_date, status(Active/...), transport_validity, non_transport_validity, user_full_name, user_image(base64), vehicle_category_details[] |

> UAT base URL uses befisc.in rather than trusthub.in (vendor-domain inconsistency in the doc).


---

## DigiLocker_Details_API

*Original zip filenames that were byte-identical duplicates of this doc:* DigiLocker_Generate_KYC_URL_API, DigiLocker_List_Docs_API


### Generate KYC URL API
`POST` `/digilocker-kyc-generate-url`

Generates a DigiLocker consent/redirect URL for a user to link their DigiLocker account for KYC.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| serviceId | yes | string | always '4' |
| uid | yes | string |  |
| firstName | yes | string |  |
| lastName | yes | string |  |
| mobile | conditional | string | mobile or emailId required |
| emailId | conditional | string |  |
| isHideExplanationScreen | no | boolean |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | string |  |
| model | object | url(short), transactionId, kycUrl(SDK redirect URL) |


### Digilocker Details API
`POST` `/digilocker-kyc-get-details`

Fetches demographic KYC details (Aadhaar-derived) for a completed DigiLocker session.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| transactionId | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | string |  |
| model | object | uniqueId, status, maskedAdharNumber, name, gender, dob, careOf, address{...}, pdfLink, image, xmlResponse |


### Digilocker List Docs API
`POST` `/digilocker-list-docs`

Lists the documents (e.g. Aadhaar, PAN card) pulled from a user's DigiLocker account, each with a presigned download URL.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| transactionId | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | string |  |
| model | array | [{url, docType, docExtension}] |
| msg | string |  |


---

## Docuflow_Status_API

*Original zip filenames that were byte-identical duplicates of this doc:* Docuflow_Cancel_Deal_API, Docuflow_Deal_Creation_API, Docuflow_Resend_Deal_Link_API


### Docuflow Deal Creation API
`POST` `/docuflow-1call`

Creates a multi-party e-sign 'deal' from either a template or an uploaded document, optionally auto-generating the agreement and initiating e-sign.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| email | yes | string |  |
| generateAgreement | yes | boolean |  |
| initiateEsign | yes | boolean |  |
| dealReferenceId | yes | string |  |
| stateCode | yes | string |  |
| productId | yes | integer |  |
| entityId | yes | string |  |
| programId | yes | integer |  |
| documentTypeId/documentUrl | conditional | string | document-based path |
| templateId/dealValue/dealPartyValue/dealNonPartySection | conditional | mixed | template-based path |
| dealParty | yes | array | partyName, partyConstituentType, partySignSequence, partySignatory[{name,email,mobile,dob,aadharNumber}] |
| callbackURL | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| dealReferenceId | string |  |
| dealStatus | string | NEW/PENDING_SIGNING/SIGNING_IN_PROGRESS/SIGN_COMPLETE/CANCELLED/... |
| dealAgreementStatus | string | NEW/GENERATED/AWAITING/INITIATED/PARTIALLY_SIGNED/COMPLETED/CANCELLED |
| message | string |  |

> This is the eSign/eStamp capability from the requirement's risk-stage 'Aadhaar eSign / Digital Signature / eStamp APIs' line.


### Docuflow Status API
`POST` `/docuflow-status`

Polls deal/agreement/signing status and returns download links for the (partially) signed PDF, as an alternative to the callback.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| dealReferenceId | yes | string |  |
| entityId | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| dealReferenceId | string |  |
| dealStatus | string |  |
| dealAgreementStatus | string |  |
| agreementPdfUrl | string |  |
| estampPdfUrl | string |  |
| dealParty | array | per-party/per-signatory sign status, signUrl, aadhaar audit metadata (post-signing only) |


### Docuflow Resend Deal Link API
`POST` `/docuflow-resend-link`

Resends the signing link (with a fresh expiry) to pending/unsigned signatories of an existing deal.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| dealRefId | yes | string |  |
| email | yes | string |  |
| expiryDate | no | string | defaults to 7 days |

**Response fields**

| Field | Type | Description |
|---|---|---|
| dealReferenceId | string |  |
| expiryDate | string |  |
| recipients | array | [{applicantName, applicantEmail, applicantMobile, id, signUrl}] |


### Docuflow Cancel Deal API
`POST` `/docuflow-cancel`

Cancels an in-progress deal, setting both deal and agreement status to CANCELLED.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| dealRefId | yes | string |  |
| email | yes | string |  |
| reasonForCancellation | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| dealReferenceId | string |  |
| dealStatus | string | CANCELLED |
| dealAgreementStatus | string |  |
| message | string |  |


---

## Dynamic_QR_Add_API

*Original zip filenames that were byte-identical duplicates of this doc:* Dynamic_QR_Status_Enquiry_API


### Add QR Code API
`POST` `/generate-qr`

Creates a static/dynamic payment QR code tied to a payment gateway, account, or payment address with configurable per-rail transaction limits.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | integer |  |
| paymentGatewayCode | yes | string | e.g. EASEBUZZ |
| uniqueReferenceNo | yes | string |  |
| label | yes | string |  |
| accountNumber | no | string |  |
| paymentAddress | no | string |  |
| autoDeactivateDate | no | string |  |
| authorisedRemitters | no | array |  |
| transactionLimits | no | object | imps(<=200000), rtgs(>=200000), neft |
| callbackUrl | no | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| uniqueReferenceNo | string |  |
| status | string |  |
| message | string |  |

> Payments/collections product, not directly a vendor-onboarding verification API.


### QR Code Status Enquiry API
`POST` `/qr-status`

Fetches QR code details, status, and downloadable QR image paths.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| uniqueReferenceNo | yes | string |  |
| entityId | yes | string |  |
| programId | yes | string |  |
| paymentGatewayCode | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| qrCodeFilePath | string |  |
| qrCodeScannerFilePath | string |  |
| qrCodeStatus | string |  |
| partnerVirtualAccountId | string |  |

> Same schema is posted to a callback URL.


---

## Electricity_Bill_API

*Original zip filenames that were byte-identical duplicates of this doc:* Electricity_Operator_Code_API


### Electricity Bill Fetch Operator
`GET` `/electricity-operator-code`

Returns the state-to-operator_code mapping table needed before calling the bill-fetch endpoint.

**Response fields**

| Field | Type | Description |
|---|---|---|
| data | array | [{state, operator_code}] |
| status_code | integer |  |
| success | boolean |  |


### Electricity Bill API
`POST` `/electricity-bill`

Fetches electricity-bill/consumer details (name, address, bill amount) for a consumer/CA number and operator code — usable as an address/utility proof.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| id_number | yes | string | CA/consumer number |
| operator_code | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| data | object | client_id, customer_id, state, full_name, address, bill_amount, bill_number, document_link |
| status_code | integer |  |
| success | boolean |  |

> Maps to the requirement's 'Electricity Account Verification'.


---

## Employment_History_API


### Employment History API
`POST` `/employment-history`

Fetches an individual's EPFO employment history (employer, joining/exit dates) using their UAN.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| id_number | yes | string | UAN |

**Response fields**

| Field | Type | Description |
|---|---|---|
| data | object | client_id, employment_history[](name, guardian_name, establishment_name, member_id, date_of_joining, date_of_exit) |
| status_code | integer |  |
| success | boolean |  |

> Relevant to 'EPFO / Employment Verification APIs' in the requirement's risk stage.


---

## FSSAI_Verification_API


### FSSAI Verification API
`POST` `/fssai-verification`

Verifies an FSSAI food-license number against consent, returning license validity/status.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| food_license_number | yes | string |  |
| consent | yes | string | Y/N |
| consent_text | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | integer | 1 success, 2 invalid, 3 inactive |
| result | object | not fully shown in doc, follows the standard KYC result pattern |

> UAT base uses sandbox-api.befisc.in (inconsistent with trusthub.in used elsewhere).


---

## Face_Match_API


### Face Match API
`POST` `/face-match`

Compares a selfie/person photo against an ID-card photo to authenticate identity and detect fraud during onboarding.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| person/person_pdf | yes(one of) | string | base64 image or PDF |
| card/card_pdf | yes(one of) | string | base64 image or PDF |
| clientRefId | yes | string | max 45 chars |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| statusCode | integer |  |
| result | object | is_same_face, is_person_image_blurry, is_card_image_blurry, same_face_confidence, person_image_correctly_identified, card_image_correctly_identified |
| clientRefId | string |  |
| reqId | string |  |

> Maps to the requirement's 'Face Match Verification'.


---

## GST_Send_OTP_API

*Original zip filenames that were byte-identical duplicates of this doc:* Advanced_GSTIN_Validation_API, GSTIN_Validation_API, GST_Submit_Request_API, PAN_to_GSTIN_Search_API


### GST Send OTP API
`POST` `/gst-send-otp`

Sends an OTP to the taxpayer's registered email to authorize a deep 'GST Fitness Report' pull (financials, related parties) — distinct from the OTP-less GSTIN Validation API.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| gst_number | yes | string |  |
| email | yes | string |  |
| financing_year | yes | string |  |
| related_party_details | no | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | integer |  |
| response | string |  |
| data | object |  |
| info | string |  |

> The zip's PAN_to_GSTIN_Search_API.pdf, Advanced_GSTIN_Validation_API.pdf, and GSTIN_Validation_API.pdf files were all byte-identical duplicates of THIS document (GST Fitness Report), not the endpoints their filenames suggest — verified via content hash. The real advanced/basic GSTIN validators and PAN→GSTIN search live under CIN_Verification_API (Company Verification APIs doc).


### GST Submit Request API
`POST` `/gst-submit-request`

Submits the requestId (obtained after the taxpayer enters the OTP out-of-band) to retrieve the GST Fitness Report.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| requestId | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| data | object | success |
| status_code | integer |  |
| message_code | string |  |
| message | string |  |
| success | boolean |  |


---

## GST_Turnover_API


### GST Turnover API
`POST` `/gst-turnover`

Returns estimated and filed GST turnover for a GSTIN and financial year, plus basic taxpayer profile (legal name, registration date, business nature).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| gst_no | yes | string |  |
| year | yes | string | YYYY-YY |
| consent | yes | string |  |
| consent_text | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | integer |  |
| result | object | estimated_turnover, turnover, total_estimated_turnover, total_turnover, gst_status, legal_name, trade_name, register_date, tax_payer_type, authorized_signatory[], business_nature[] |

> Useful for the requirement's financial-analytics stage (turnover-based risk banding).


---

## ITR_Download_Profile_API

*Original zip filenames that were byte-identical duplicates of this doc:* ITR_Create_Credentials_API, ITR_Validate_Credentials_API


### ITR Create Credentials API
`POST` `/itr-create-credentials`

Registers income-tax portal login credentials with TransBnk to create an ITR client profile for later report pulls.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| username | yes | string | PAN as ITR portal login |
| password | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| data | object | client_id |
| status_code | integer |  |
| message_code | string |  |
| message | string |  |
| success | boolean |  |

> 3-step flow: Create Credentials -> Validate Credentials -> Download Profile.


### ITR Validate Credentials API
`POST` `/itr-validate-credentials`

Validates that the created ITR client profile's credentials still work / the account exists.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| client_id | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| data | object | success(boolean) |
| status_code | integer |  |


### ITR Download Profile API
`POST` `/itr-download-proﬁle`

Downloads the taxpayer's ITR portal profile: address, PAN details, contact, jurisdiction, Aadhaar link status.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| client_id | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| data | object | profile_details{address,pan,contact,jurisdiction,aadhaar} |
| status_code | integer |  |
| success | boolean |  |

> Maps to the requirement's 'ITR Financial Analysis'. Path contains a unicode ligature 'ﬁ' in the source doc — verify exact bytes before hard-coding.


---

## LPG_Verification_API


### LPG Mobile Verification API
`POST` `/lpg-mv`

Verifies LPG gas-connection details (provider, consumer id/status, distributor) linked to a mobile number.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mobile | yes | string |  |
| consent | yes | string |  |
| consent_text | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | integer |  |
| result | array | [{gas_provider, name, consumer_details{consumer_mobile,consumer_id,consumer_status,consumer_type}, address, distributor_details{...}}] |

> Maps to the requirement's 'LPG Verification'.


---

## Mobile_Name_Match_API

*Original zip filenames that were byte-identical duplicates of this doc:* Mobile_Number_Validation_API_No_Consent


### Mobile Number Validation API (no consent)
`POST` `/mobile-number-validation`

Validates an Indian mobile number and returns connection/porting/service-provider details without user consent or OTP.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mobile | yes | string |  |
| options | no | array | customer_details, porting_history, ported_date |
| client_ref_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result_code | integer |  |
| result | object | is_valid, subscriber_status, connection_status, connection_type, msisdn, current_service_provider, original_service_provider, is_roaming, is_ported, last_ported_date, porting_history[] |

> This is the requirement's 'Mobile Number Verification – No Consent'.


### Mobile Number To Name Matching API
`POST` `/mobile-name-match`

Returns the name linked to a mobile number and, if a name is supplied, a fuzzy match score against it.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mobile | yes | string |  |
| name | no | string |  |
| client_ref_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result_code | integer |  |
| result | object | mobile_linked_name, name_match(bool), name_match_score(>=75 => match) |

> This is the requirement's 'Mobile Subscriber Name'.


---

## Mobile_Number_Validation_Get_Status_API

*Original zip filenames that were byte-identical duplicates of this doc:* Mobile_Number_Validation_Initiate_OTP_API, Mobile_Number_Validation_Submit_OTP_API


### Initiate Mobile Number Validation
`POST` `/mobnvalid-initiate-otp`

Starts OTP-based-consent mobile validation; sends an OTP to the subscriber and returns a txn_id/token pair.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| purpose | yes | string | 'initiate_request' |
| client_ref_num | yes | string |  |
| mobile_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| txn_id | string |  |
| token | string |  |
| txn_status_code | string | OtpRequired and various error codes |
| operator_name | string |  |

> This is the requirement's 'Mobile Number Verification – Consent', a 3-step flow: Initiate -> Submit OTP -> Get Status.


### Submit OTP
`POST` `/mobnvalid-submit-otp`

Submits the subscriber-entered OTP to consent-validate the mobile number.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| purpose | yes | string | 'submit_otp' |
| txn_id | yes | string |  |
| token | yes | string |  |
| otp_value | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| txn_id | string |  |
| txn_status_code | string | 'OtpSubmitted' |
| msg | string |  |


### Get Status
`POST` `/mobnvalid-get-status`

Fetches the full subscriber report (identity, contact, device, plan, SIM, billing/recharge history, porting/roaming) once OTP is validated.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| purpose | yes | string | 'get_status' |
| txn_id | yes | string |  |
| token | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| txn_id | string |  |
| report | object | result.identity_details, contact_details, device_details, plan_details, extra_details, history{billing/payment/recharge}, sim_details, is_ported, is_roaming |
| txn_status_code | string | 'ReportGenerated' |


---

## Mobile_Number_to_VPA_API


### Mobile Number to VPA Lookup API
`POST` `/mobile2vpa`

Looks up the UPI VPA(s) and linked name/IFSC associated with a mobile number.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mobile | yes | string |  |
| name | no | string |  |
| client_ref_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result | object | mobile_linked_name, vpa, account_ifsc, name_match, name_match_score |

> Also supports AES-256-ECB encrypted_payload mode. Maps to 'Mobile-to-UPI Address' in the requirement.


---

## Mobile_Prefill_API


### Mobile To Prefill API
`POST` `/mobile-to-prefill`

Given a mobile number + name, returns the linked PAN and full PAN-holder profile (name, address, email, DOB, Aadhaar-linked) for form prefill.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mobile | yes | string |  |
| name | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| data | object | client_id, mobile_no, name, pan_number, pan_details{full_name, full_name_split, masked_aadhaar, address{...}, email, phone_number, gender, dob, aadhaar_linked, category} |

> Maps to the requirement's 'Mobile-Based Profile Prefill'.


---

## Mobile_to_PAN_API


### Mobile To PAN API
`POST` `/mobile-to-pan`

Returns the PAN number linked to a given mobile number and name.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| name | yes | string |  |
| mobile_no | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| data | object | client_id, name, mobile_no, pan_number |

> Maps to the requirement's 'Phone to PAN Verification'.


---

## Mobile_to_Udyam_API


### Mobile to Udyam API
`POST` `/mobile-to-udyam`

Looks up Udyam MSME registration number(s) and enterprise name linked to a mobile number.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mobile | yes | string |  |
| consent | yes | string |  |
| consent_text | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | integer |  |
| result | array | [{udyam_number, enterprise_name}] |

> This is the requirement's 'PAN to Udyam Details Lookup' analogue, but keyed by mobile not PAN — no direct PAN-to-Udyam endpoint was found in this doc set.


---

## NACH_Mandate_Request_API

*Original zip filenames that were byte-identical duplicates of this doc:* NACH_Bulk_Presentation_Request_API, NACH_Bulk_Presentation_Status_API, NACH_Mandate_Status_Enquiry_API, NACH_Presentation_Request_API, NACH_Presentation_Status_API


### NACH Mandate Request API
`POST` `/nach-mandate-request`

Requests an e-NACH (recurring debit) mandate from a customer's bank account; returns a customerUrl for the customer to authenticate the mandate.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| user | yes | string |  |
| password | yes | string |  |
| entityId | yes | string |  |
| programId | yes | string |  |
| external1RefId | yes | string |  |
| categoryCode | yes | string | L001/L002/S001 |
| sequenceType | yes | string | RCUR |
| frequency | yes | string |  |
| firstCollectionDate | yes | string |  |
| debitType | yes | string | FIXED_AMOUNT/MAXIMUM_AMOUNT |
| collectionAmount | yes | number |  |
| customerName | yes | string |  |
| accountHolderName/accountNumber/accountType | conditional | string |  |
| authType | no | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| id | string | NACH reference number |
| customerUrl | string | mandate authentication URL |

> This is a bank-account-mandate/payment-readiness API, uses basic-auth-style user/password in addition to x-api-key.


### NACH Mandate Status Enquiry API
`POST` `/nach-mandate-status`

Checks the status of a previously requested NACH mandate (PENDING through COMPLETED/REJECTED).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| user | yes | string |  |
| password | yes | string |  |
| nachRefNo | yes | string |  |
| entityId | yes | string |  |
| programId | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| id | string |  |
| status | string |  |
| umrn | string | present once COMPLETED |
| accountHolderName/accountNumber/accountType/bankIfsc | string |  |

> Same payload shape is used for the webhook callback.


### NACH Presentation Request API
`POST` `/nach-presentation-request`

Presents (executes) a single debit against an already-registered NACH mandate (UMRN).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| umrn | yes | string |  |
| presentationAmount | yes | number |  |
| settlementDate | yes | string |  |
| isUmrnExists | yes | integer |  |
| presentationRequestType | yes | string | 'DR' |

**Response fields**

| Field | Type | Description |
|---|---|---|
| id | string |  |
| externalReferenceNo | string |  |
| umrn | string |  |
| status | string | PENDING...COMPLETED/REJECTED/CANCELLED |


### NACH Bulk Presentation API
`POST` `/nach-bulkpresentation-request`

Submits many NACH debit presentations in one batched call.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityBatchNumber | yes | string |  |
| presentationRequests | yes | array |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| entityBatchNumber | string |  |
| presentationResponseList | array |  |
| presentationFailedList | array | [{umrn, rejectedReason[{code:msg}]}] |


### NACH Presentation Status Enquiry API
`POST` `/nach-presentation-status`

Checks status of a single presentation by externalReferenceNo.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| externalReferenceNo | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| (array) | array | [{id, externalReferenceNo, umrn, status, statusRemark, npciRespondedAt, createdAt}] |


### NACH Bulk Presentation Status Enquiry API
`POST` `/nach-bulkpresentation-status`

Checks status of all presentations submitted under a batch.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityBatchNumber | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| (array) | array | same shape as single presentation status, one entry per row |


---

## PAN_Advanced_API


### PAN Advanced
`POST` `/pan-advanced-2`

Verifies a PAN and returns detailed KYC data: name parts, DOB, masked email/phone/Aadhaar, address, PAN status/category.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| input | yes | object | panNumber(regex ^[A-Z]{5}[0-9]{4}[A-Z]$), consent(true) |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| requestId | string |  |
| serviceStatusCode | integer |  |
| data | object | panNumber, fullName/firstName/middleName/lastName, dob, gender, email, phoneNumber, maskedAadhaar, aadhaarLinked, panStatus, panCategory, address{...}, panIssueDate, lessInfo |
| vendorResponse | array |  |

> Maps to the requirement's 'PAN Advanced Verification'.


---

## PAN_Basic_API


### PAN Check API
`POST` `/pan-details`

Authenticates a PAN and returns basic holder details.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| isUserConsent | yes | string | 'y'/'n' |
| panId | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | boolean |  |
| message | string |  |
| data | object | client_id, pan_number, full_name, ... |

> This is the requirement's 'PAN Basic / Lite Verification'; UAT has a fixed success PAN for testing.


---

## PAN_Supreme_API


### PAN Supreme V2
`POST` `/pan-supreme-v2`

Retrieves comprehensive PAN-linked KYC details including father's name, masked Aadhaar, and full address — the most complete PAN profile in this API set.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| pan | yes | string |  |
| consent | yes | string |  |
| consent_text | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| txn_id | string |  |
| status | number |  |
| result | object | full_name/first_name/middle_name/last_name, masked_aadhaar, address{...}, email, phone_number, gender, dob, aadhaar_linked, category, fname(father's name) |

> Maps to the requirement's 'PAN Comprehensive KYC' / 'PAN-Based KYC Verification'.


---

## PAN_To_Aadhaar_API


### PAN To Aadhaar API
`POST` `/pan2aadhaar-search`

Checks whether a PAN is linked to Aadhaar and returns the masked Aadhaar number if so.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| pan | yes | string |  |
| client_ref_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result_code | integer |  |
| result | object | linked('y'/'n'), aadhaar_number(masked) |

> This is the requirement's 'PAN-Aadhaar Linkage Verification'.


---

## Passbook_Retrieval_API_UAN_Based


### Passbook Details API
`POST` `/get-passbook`

Retrieves an individual's EPF passbook(s) by UAN: employer establishment details plus month-wise employee/employer contributions and overall PF balance.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| client_ref_num | yes | string |  |
| uan | yes | string | 10-12 digit UAN |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result_code | integer |  |
| result | object | employee_details{uan,member_name,dob}, est_details[](est_name, member_id, office, doj_epf, passbook_status, passbook[]), overall_pf_balance{pension_balance, current_pf_balance, employee_share_total, employer_share_total} |

> Overlaps with Employment_History_API but returns transaction-level PF passbook, not just tenure.


---

## Payment_Gateway_Link_Status_API

*Original zip filenames that were byte-identical duplicates of this doc:* Payment_Gateway_Link_Creation_API


### Payment Gateway Link Creation API
`POST` `/pg-link`

Creates a hosted payment-collection link and can notify the customer via SMS/Email/WhatsApp.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| paymentGatewayCode | yes | string |  |
| uniqueReferenceNo | yes | string |  |
| customerName | yes | string |  |
| customerPhone | yes | string |  |
| amount | yes | string |  |
| expiryDate | no | string |  |
| communication | no | object | type(SMS/EMAIL/WHATSAPP), templateId |

**Response fields**

| Field | Type | Description |
|---|---|---|
| (not shown in doc; exact schema in image not extracted as text) | object |  |

> Response tables in this doc are images and weren't OCR'd to text — verify exact response schema from the PDF if this endpoint is implemented.


### Payment Gateway Link Status Fetch API
`POST` `/pg-link-status`

Fetches the status of a previously created payment link.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| uniqueReferenceNo | yes | string |  |
| entityId | yes | string |  |
| programId | yes | string |  |
| paymentGatewayCode | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| (not shown in doc) | object |  |

> Same OCR limitation as the creation endpoint.


---

## Section_206AB_Compliance_API


### 206AB Check API
`POST` `/206ab`

Verifies whether a PAN is a 'specified person' under Income Tax Section 206AB (higher TDS/TCS applicability) and returns PAN allotment/status.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| pan | yes | string |  |
| consent | yes | string |  |
| consent_text | yes | string | must match an exact prescribed sentence |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | integer |  |
| result | object | pan_number, masked_name, pan_allotment_date, pan_status, specified_person(Yes/No) |

> Directly relevant to vendor tax-compliance screening before payment (TDS rate determination).


---

## TransBnk_Experian_API


### TransBnk Experian API
`POST` `/experian-report-3`

Fetches an Experian credit score and full credit report for an individual by name, mobile, and PAN.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| name | yes | string |  |
| mobile | yes | string |  |
| pan | yes | string |  |
| consent_text | yes | string |  |
| consent | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | integer |  |
| result | object | credit_score, credit_report{CreditProfileHeader, Current_Application, CAIS_Account(summary+per-account details+history), Match_result, CAPS/NonCreditCAPS enquiry summaries, SCORE} |

> Second credit-bureau option alongside CIBIL_API, for the requirement's 'Credit Bureau Reports – CIBIL/Experian/CRIF/Equifax'.


---

## TransBnk_Mobile_to_ESIC_Details_API


### Mobile to ESIC Details API
`POST` `/mobile2eisc`

Retrieves ESIC (employee state insurance) registration details — employer, UAN, bank, dispensary — linked to a mobile number.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mobile | yes | string |  |
| consent | yes | string |  |
| consent_text | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | integer |  |
| result | object | mobile_no, esic_details[](esic_number, name, employer_code/name, uan_number, bank_name, bank_account_status, employer_details{...}, address, age, gender) |

> Individual/employee verification, not directly vendor-entity KYB, but useful for signatory/employee checks.


---

## Two_Point_Distance_API

*Original zip filenames that were byte-identical duplicates of this doc:* Address_to_Latitude-Longitude_API, Latitude-Longitude_to_Address_API


### Address to Latitude-Longitude API
`POST` `/addr2latlong`

Geocodes a free-text postal address into latitude/longitude.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| uniqueId | yes | string |  |
| address | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | string |  |
| model | object | latitude, longitude |

> Part of the requirement's 'Address & Geolocation Verification' trio.


### Latitude-Longitude to Address API
`POST` `/latlong2addr`

Reverse-geocodes coordinates into a postal address (pincode, district, state).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| uniqueId | yes | string |  |
| latitude | yes | string |  |
| longitude | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | string |  |
| model | object | address, pincode, district, state |


### Two Point Distance API
`POST` `/2pt-distance`

Computes the distance in kilometers between two lat/long coordinate pairs.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| uniqueId | yes | string |  |
| fromLocation | yes | object | latitude, longitude |
| toLocation | yes | object |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| code | string |  |
| model | object | message, distance(km) |

> Field-visit/serviceability use case, not core KYC — likely out of scope for a vendor-onboarding MVP.


---

## UPI_Autopay_Validate_VPA_API

*Original zip filenames that were byte-identical duplicates of this doc:* UPI_Autopay_Check_Mandate_Status_API, UPI_Autopay_Create_Collection_API, UPI_Autopay_Create_Mandate_API, UPI_Autopay_Mandate_Revoke_API, UPI_Autopay_Pre-Debit_Notification_API, UPI_Autopay_Transaction_Status_API


### Validate VPA API
`POST` `/upiap-validate-vpa`

Validates a UPI VPA and returns the linked account-holder's masked name (with optional exact-name match) ahead of setting up a UPI Autopay mandate.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| entityId | yes | string |  |
| programId | yes | string |  |
| merchantId | yes | string |  |
| referenceNo | yes | string |  |
| vpa | yes | string |  |
| merchantMobile/merchantDeviceGeoCode/merchantDeviceLocation/merchantDeviceIP/merchantDeviceType/merchantDeviceId/merchantDeviceOS/merchantDeviceAppName | no | string | merchant device fingerprint fields |

**Response fields**

| Field | Type | Description |
|---|---|---|
| referenceNo | string |  |
| status | string | VALID/INVALID |
| vpaMaskedName | string |  |
| vpaIfscCode | string |  |
| vpaType | string | PERSON/ENTITY |
| payerName | string |  |
| accountType | string |  |

> Identical endpoint/content to the separately-filed VPA_UPI_ID_Validation_API doc (confirmed by hash within the same doc family naming). Maps to the requirement's 'VPA to Name Lookup' / 'VPA to IFSC & Name Match'.


### Create Mandate Request API
`POST` `/upiap-mandate-request`

Registers a new UPI Autopay recurring-debit mandate for a payer VPA.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| merchantId | yes | string |  |
| referenceNo | yes | string |  |
| purposeCode | yes | string | 01 one-time / 14 recurring |
| mandateStartDate/mandateEndDate | yes | string |  |
| recurrenceFrequency | yes | string |  |
| amount | yes | number |  |
| amountRule | yes | string | MAX/EXACT |
| payerVpa | yes | string |  |
| payerName | yes | string |  |
| accountValidation/accountNo | conditional | mixed |  |
| actionOnRegn/actionOnFirstDebitFail | no | string | optional Rs1 first-debit verification with auto-revoke-on-fail |

**Response fields**

| Field | Type | Description |
|---|---|---|
| id | string |  |
| status | string | SB_CREATION_AWAITING / SB_INTENT_SUCCESS |
| customerReferenceNo | string |  |
| errorCode | string |  |

> Payments/collections product — not vendor-onboarding verification itself, but usable for recurring-payment readiness.


### Check Mandate Status API
`POST` `/upiap-mandate-status`

Polls status of a mandate create/revoke request; returns UMN and full mandate detail once active.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| referenceNo | yes | string |  |
| originalReferenceNo | yes | string |  |
| mandateAction | no | string | CREATE/REVOKE |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string | PENDING/SUCCESS/FAILURE |
| mandateUMN | string |  |
| mandateStatus | string | ACTIVE/PENDING |
| payerVpa/payerName/payeeVpa/payeeName | string |  |


### Pre-Debit Notification API
`POST` `/upiap-predebit-notify`

Requests the payee bank to send the mandatory pre-debit notification to the payer ahead of an autopay execution.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mandateUMN | yes | string |  |
| amount | yes | number |  |
| mandateNextExecutionTimestamp | yes | string |  |
| executionSequenceNumber | yes | integer |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| id | string |  |
| status | string | SB_PREDEBIT_INVOKED |
| customerReferenceNo | string |  |


### Create Mandate Collection API
`POST` `/upiap-mandate-collection`

Executes (collects) a debit against an active UPI Autopay mandate.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mandateUMN | yes | string |  |
| amount | yes | number |  |
| executionSequenceNumber | yes | integer |  |
| payerVpa/payerName | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| id | string |  |
| status | string | SB_COLLECTION_INVOKED / SB_COLLECTION_FAILED |
| customerReferenceNo | string |  |

> Can only be called 24-48h after mandate creation succeeds.


### Transaction Status Enquiry API
`POST` `/upiap-mandate-txnstatus`

Checks the status of a mandate collection/creation transaction (same shape as Check Mandate Status).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| referenceNo | yes | string |  |
| originalReferenceNo | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | string |  |
| mandateUMN | string |  |


### Mandate Revoke API
`POST` `/upiap-mandate-revoke`

Revokes an active UPI Autopay mandate.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| mandateAction | yes | string | 'REVOKE' |
| mandateUMN | yes | string |  |
| amount | yes | number |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| id | string |  |
| status | string | SB_REVOKE_SUCCESS |
| customerReferenceNo | string |  |


---

## Udyam_Verification_API

*Original zip filenames that were byte-identical duplicates of this doc:* Udyam_Verification_API (1)


### Udyam Verification API
`POST` `/udyam-verification`

Verifies a Udyam (MSME) registration number and returns enterprise details.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| registration_no | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | integer | 1 success, 2/3 invalid/inactive |
| result | object | exact fields not OCR'd (image-based table in doc) but follows the standard status/result pattern |

> This is the requirement's 'Udyam to Udyam Details' / core Udyam Verification API; response field table was an image in the source PDF.


---

## VPA_UPI_ID_Validation_API


### Validate VPA API (duplicate)
`POST` `/upiap-validate-vpa`

Same endpoint as UPI_Autopay_Validate_VPA_API's Validate VPA API — filed here under a standalone 'VPA Validation API' title.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| (see UPI_Autopay_Validate_VPA_API) | n/a | n/a |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| (see UPI_Autopay_Validate_VPA_API) | n/a |  |

> Kept as a separate reference row only to record that two source docs describe the identical live endpoint.


---

## Vehicle_RC_Verification_API


### Vehicle RC Validation Request API
`POST` `/validate-vehiclerc`

Fetches full vehicle RC details (owner, chassis/engine, insurance, permit, PUC, addresses) for a registration number.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| reg_no | yes | string |  |
| client_ref_num | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| result_code | integer | 101 success |
| result | object | reg_no, class, chassis, engine, vehicle_manufacturer_name, owner_name, status, reg_date, rc_expiry_date, vehicle_insurance_*, present_address/permanent_address + split, pucc_number/upto, permit_* |

> Not in the requirement's explicit list but useful for vendor fleet/logistics KYC if relevant.


---

## Virtual_Gift_Card_Issuance_API


### Virtual Gift Card Create API
`POST` `/virtual-gift-card-create`

Issues a virtual gift card for a customer (KYC-lite: name/DOB/doc/email/gender/amount); processed asynchronously.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| name | yes | string |  |
| mobile | yes | string |  |
| dateOfBirth | yes | string |  |
| documentType | yes | string |  |
| documentValue | yes | string |  |
| email | yes | string |  |
| gender | yes | string |  |
| amount | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | object | code(2000 success), message |
| result | object | message, request_id |

> Rewards/incentive product, not vendor-onboarding relevant; uses the same x-client-id/x-username/x-client-password headers as the Prepaid Card suite.


### Virtual Gift Card Status API
`POST` `/virtual-gift-card-status`

Polls the creation status of a virtual gift card by cardId/mobile.

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| cardId | yes | string |  |
| mobile | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | object |  |
| result | object | message, card_id, status(SUCCESS/FAILURE) |


---

## Voter_ID_Verification_API


### Voter Details API
`POST` `/voter-details`

Retrieves electoral-roll details (name, age, gender, constituency, polling booth, address) for a Voter ID (EPIC number).

**Request fields**

| Field | Required | Type | Description |
|---|---|---|---|
| voter | yes | string |  |

**Response fields**

| Field | Type | Description |
|---|---|---|
| status | integer | 1 success, 2 invalid |
| result | object | address{district,state}, user_age, user_gender, user_name_english, assembly/parliamentary constituency details, polling_booth{...}, relative_name/relation, epic_number, voter_last_updated_date |

> Maps to the requirement's 'Voter ID Verification'.


---
