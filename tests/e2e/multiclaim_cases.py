"""
A case set of REAL multi-claim inputs, with the author's own demand held back.

Built by `screen_multiclaim_inputs.py` on 2026-10-26 and committed because a
measured figure must rest on a fixed set. Read that module first: it says why
the inputs are not written here (inputs authored by someone who knows the rule
pass the rule), where they come from, and how the blind screen chose them.

Source: UK Parliament petitions, https://petition.parliament.uk — all content
there is available under the Open Government Licence v3.0. Each item keeps its
petition id and URL, so every text is attributable and re-fetchable.

WHAT EACH FIELD IS FOR
======================
`text` is the petition's own argument (`background` + `additional_details`) and
is the ONLY field a writer under test may see. `demand` is the author's separate
one-line petition `action`: the claim they would sign, written by them, never
shown to the framework — it is the ground truth for
`view_sketch.THESIS_IS_A_STANCE`'s last sentence. `conceded` is the clause in
which the text names an opposing view and grants it, quoted by the blind screen;
where it is not None, the item also serves
`antithesis_extraction._OPPOSING_POSITION_ASK`'s mirror, whose A+ must not be
that clause.

TWO SETS
========
`MULTI_CLAIM_CASES` is the first set (2026-10-26, morning). Its first run was a
dead null (19/40 either arm), and inspection showed why: a petition OPENS with
its demand, so in 31 of 40 the demand sat in the text's first third and was
drawn right by position alone — the rule under test is about choosing the
signable claim over the hedges that PRECEDE it, which this set rarely poses.
`MULTI_CLAIM_CASES_LATE` is the second set, built the same day for that shape:
candidates were pre-filtered, on the author's `action` alone, for a demand
stated in NO sentence of the first half and in SOME sentence of the second
(78 of 4,624 length-qualified petitions), then put through the same blind
screen, which passed 41; the first 40 by petition id are here. None concedes an
opposing view by the screen's read, so the mirror rule's cases stay in the first
set. `claims` on every case is the blind screen's own list of the text's distinct
claims, in text order — the options the second instrument chooses among.

COMPOSITION OF THE FIRST SET, stated because it is not a random sample
=======================================================================
40 items of the 149 the screen passed: ALL 22 that concede an opposing view,
plus the first 18 of the rest by petition id. So the set deliberately
over-samples conceding texts, because they are what the mirror rule needs and
they are the harder cases for the which-claim rule too — a conservative bias for
rule 1, and the only way to have cases at all for rule 2. Within each group the
order is petition id, which is arbitrary with respect to content: no item was
picked or dropped by reading it.

LIMITATIONS to state wherever a figure from this set is quoted
==============================================================
- A petition is a demand by construction, so this set tests "which of several
  claims" where one of them is unmistakably a demand. It does NOT test an input
  whose strongest claim is implicit.
- In 2 of the first 40 the author's `demand` also appears verbatim inside `text`.
  That is not a leak to remove: the handoff's own case contained "Stop masinei
  migracijai" verbatim and the writer still drew a tetrad about the hedge. It is
  recorded so a per-item result can be read against it.
- Registers are mixed: some items are institutional ("We call on the
  Government to ..."), others first-person and informal. Both are real, neither
  was selected for.
- Every item carries the person's OWN position. Material that is not the
  reader's stance — an article, someone else's transcript — is a different
  question and needs its own set (CLAUDE.md, the view turn's input kinds).
"""

from __future__ import annotations

from typing import NamedTuple, Optional



class MultiClaimCase(NamedTuple):
    """One real argument, its author's demand, its conceded opposition, and the
    blind screen's list of the claims it makes."""

    petition_id: str
    text: str
    demand: str
    conceded: Optional[str]
    claims: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        return f"https://petition.parliament.uk/petitions/{self.petition_id}"


#: The first 40. `text` is what a writer under test sees; nothing else.
MULTI_CLAIM_CASES: tuple[MultiClaimCase, ...] = (
    MultiClaimCase(
        petition_id="307220",
        text=(
            "To make an allowance for religious wishes in the proposed Coronavirus Bill and to "
            "stop forced cremation of loved ones which would be against the customs and rules of "
            "religious minorities in the country. Forcing cremation risks causing anxiety, "
            "depression and poor mental health for people. Under the proposed Schedule 27 of the "
            "Coronavirus Bill relating to disposal of dead bodies the government proposes "
            "suspending the wishes of the deceased to not be cremated. Cremation is against the "
            "religious rulings followed by many people of the Jewish and Muslim faiths. Many "
            "religious groups have suspended prayer gatherings to support the public efforts "
            "against COVID19. However forcing cremation of loved ones could cause immense undue "
            "emotional strain and seriously impact mental health."
        ),
        demand=(
            "COVID19: RESPECT RELIGIOUS WISHES FOR BURIALS AND STOP FORCED CREMATIONS"
        ),
        conceded=(
            "Many religious groups have suspended prayer gatherings to support the public efforts "
            "against COVID19. However forcing cremation of loved ones could cause immense undue "
            "emotional strain and seriously impact mental health."
        ),
        claims=(
            "The Coronavirus Bill should allow for religious wishes and stop forced cremation of "
            "loved ones",
            "Forced cremation goes against the customs and rules of religious minorities",
            "Forced cremation risks causing anxiety, depression and poor mental health",
            "Schedule 27 of the Coronavirus Bill proposes suspending the deceased's wishes not to "
            "be cremated",
            "Cremation is against the religious rulings followed by many Jewish and Muslim people",
            "Many religious groups have suspended prayer gatherings to support public efforts "
            "against COVID19",
            "Forced cremation could cause immense undue emotional strain and seriously impact "
            "mental health",
        ),
    ),
    MultiClaimCase(
        petition_id="307609",
        text=(
            "Allow Self Employed Sole Traders to claim 80% of their average annual income due to "
            "loss of earnings caused by the Corona Virus Epidemic. The income should be "
            "calculated by finding the average earnings from the last 3 years. The weekly income "
            "support should last 3 months and be reviewed regularly. Whilst businesses have been "
            "strongly supported by the government during these times, Sole Traders and Self "
            "Employed people have not been given adequate financial backing from the government "
            "to help them and their families survive. £90 a week sick pay does not cover living "
            "costs for families. We should be offered the same help as those that are employed. "
            "Our outgoings and living costs are no different to those that are employed, and what "
            "we can claim should reflect that."
        ),
        demand=(
            "Allow Self Employed Sole Traders to claim 80% of their average annual income"
        ),
        conceded=(
            "Whilst businesses have been strongly supported by the government during these times"
        ),
        claims=(
            "Self-employed sole traders should be able to claim 80% of their average annual "
            "income for loss of earnings due to the Coronavirus epidemic",
            "Income should be calculated as the average earnings over the last 3 years",
            "Weekly income support should last 3 months and be reviewed regularly",
            "Businesses have been strongly supported by the government, but sole traders and the "
            "self-employed have not been given adequate financial backing",
            "£90 a week sick pay does not cover families' living costs",
            "The self-employed should be offered the same help as the employed",
            "The self-employed have the same outgoings and living costs as the employed, so what "
            "they can claim should reflect that",
        ),
    ),
    MultiClaimCase(
        petition_id="308031",
        text=(
            "We must stop unnecessary travel to this county in order to protect our NHS and save "
            "the lives our our citizens. We must force all travel companies, campsites and "
            "holiday providers to stop selling accommodation throughout the COVID19 disaster and "
            "cancel upcoming bookings until further notice. Holiday letting company's, campsites "
            "and private rentals all continue to promote and sell. We in Cornwall above all "
            "understand the need to keep businesses open and how vital the hospitality sector in "
            "this county is to putting food on the tables for thousands of Cornish families each "
            "year. This however is not about income. It is about lives and we urge you to help us "
            "at this critical time."
        ),
        demand=(
            "Stop holiday travel company's selling breaks to Cornwall throughout COVID19."
        ),
        conceded=(
            "We in Cornwall above all understand the need to keep businesses open and how vital "
            "the hospitality sector in this county is to putting food on the tables for thousands "
            "of Cornish families each year."
        ),
        claims=(
            "Unnecessary travel to the county must stop to protect the NHS and save lives",
            "Travel companies, campsites and holiday providers must be forced to stop selling "
            "accommodation and cancel upcoming bookings until further notice",
            "Holiday letting companies, campsites and private rentals are still promoting and "
            "selling",
            "Cornwall understands the need to keep businesses open and the hospitality sector is "
            "vital to thousands of Cornish families",
            "This is about lives, not income, and the reader is urged to help",
        ),
    ),
    MultiClaimCase(
        petition_id="308084",
        text=(
            "I want the parliament to view BTEC the same way that they’re viewing A-levels and "
            "GCSE. Having done GCSE a lot of people can all agree that it’s almost pointless as "
            "long as you achieve a good grade in Maths English and science all the other subjects "
            "were pretty much useless so giving GCSE. Give all BTEC students their predicted "
            "grades as BTEC student are affected by this pandemic as much as A-level students and "
            "it doesn’t make sense to give one their predicted grade but not the other. I "
            "understand that A-level students needs to take exam and so on which you can argue is "
            "a lot harder than BTEC but I can assure you BTEC students work just as hard we have "
            "more Units to work and we don’t always have the best teachers in essence as a BTEC "
            "student we feel neglected"
        ),
        demand=(
            "Give all BTEC students their predicted grades."
        ),
        conceded=(
            "I understand that A-level students needs to take exam and so on which you can argue "
            "is a lot harder than BTEC"
        ),
        claims=(
            "Parliament should treat BTEC the same way it treats A-levels and GCSEs",
            "GCSEs are almost pointless apart from good grades in Maths, English and science",
            "All BTEC students should be given their predicted grades",
            "BTEC students are affected by the pandemic as much as A-level students",
            "It makes no sense to give one group predicted grades but not the other",
            "A-levels are arguably harder than BTEC and need exams",
            "BTEC students work just as hard, with more units and not always the best teachers",
            "BTEC students feel neglected",
        ),
    ),
    MultiClaimCase(
        petition_id="308592",
        text=(
            "Universities should not expect students now having to move to virtual learning to "
            "pay the same fees as those originally signed up for. Virtual learning is not the "
            "same quality experience as learning in class so the government should make them "
            "reduce fees in line with online education providers. The coronavirus has shattered "
            "the lives of students- with many losing jobs, isolating alone in still-unfamiliar "
            "areas without friends, family or classmates for company, and therefore struggling "
            "with their mental health. Whilst Unis are no doubt working hard to reach need, the "
            "shift towards virtual learning is not the experience originally desired and is "
            "adding additional stress to their lot. If the mode of delivery is no different to "
            "say the OU, then Unis should price match their course fees."
        ),
        demand=(
            "Require Universities to reduce Tuition fees during the Coronavirus pandemic"
        ),
        conceded=(
            "Whilst Unis are no doubt working hard to reach need, the shift towards virtual "
            "learning is not the experience originally desired"
        ),
        claims=(
            "Universities should not charge students moved to virtual learning the same fees as "
            "originally signed up for",
            "Virtual learning is lower quality than in-class learning",
            "The government should make universities reduce fees in line with online education "
            "providers",
            "The coronavirus has shattered students' lives (job losses, isolation, mental health "
            "struggles)",
            "Universities are working hard to meet students' needs",
            "The shift to virtual learning is not the experience originally desired and adds "
            "stress",
            "If delivery is no different from the OU, universities should price match their "
            "course fees",
        ),
    ),
    MultiClaimCase(
        petition_id="308917",
        text=(
            "Lower or change the requirements that registered nurses in UK from overseas must "
            "meet to register with the Nursing and Midwifery Council to allow them to work during "
            "the Covid-19 pandemic. The Nursing and Midwifery Council is responsible for "
            "maintaining the standards that nurses must meet to work safely. However, 2 tests, 3 "
            "if you are not from an English country, makes the registration process long, costly "
            "and difficult for overseas nurses to work in the UK. I have a degree which shows "
            "thousands of theoretical and practical hours, as well as many written and practical "
            "tests. Now during a pandemic I am not able to work. This is regarding overseas "
            "nurses already living in UK."
        ),
        demand=(
            "Lower NMC requirement to let registered nurses from overseas work during Covid19"
        ),
        conceded=(
            "The Nursing and Midwifery Council is responsible for maintaining the standards that "
            "nurses must meet to work safely. However, 2 tests, 3 if you are not from an English "
            "country, makes the registration process long, costly and difficult"
        ),
        claims=(
            "Registration requirements for overseas nurses in the UK should be lowered or changed "
            "during the Covid-19 pandemic",
            "The Nursing and Midwifery Council is responsible for maintaining standards nurses "
            "must meet to work safely",
            "The 2 tests (3 for non-English-country applicants) make registration long, costly "
            "and difficult for overseas nurses",
            "The author holds a degree showing thousands of theoretical and practical hours plus "
            "many written and practical tests",
            "The author cannot work during the pandemic",
            "The request applies to overseas nurses already living in the UK",
        ),
    ),
    MultiClaimCase(
        petition_id="310280",
        text=(
            "Since the outbreak developed in Febraury 2020, NHS staff, carers, police, fire, "
            "cleaners and food retail have stepped up and are working ridiculous amount of hours. "
            "They do not get any hazard pay for this, a tax exemption backdated to the start of "
            "the year would go some way to repay the debt. Putting their own lives at risk, they "
            "are still helping the vulnerable during lockdown and dont receive any hazard pay. "
            "The country has pulled together and the staff in these jobs are not able to see "
            "their family. A pay rise would be difficult to put in place by companies however "
            "allowing a tax exemption would potentially give more back to say thank you for your "
            "service."
        ),
        demand=(
            "All key workers to receive a tax exemption during COVID-19"
        ),
        conceded=(
            "A pay rise would be difficult to put in place by companies however allowing a tax "
            "exemption would potentially give more back to say thank you for your service."
        ),
        claims=(
            "Frontline workers (NHS staff, carers, police, fire, cleaners, food retail) have "
            "stepped up since the outbreak began in February 2020 and are working excessive hours",
            "These workers receive no hazard pay despite the risks they take",
            "A tax exemption backdated to the start of the year would help repay the debt owed to "
            "them",
            "They put their own lives at risk to help the vulnerable during lockdown",
            "They cannot see their families while the country has pulled together",
            "A pay rise would be difficult for companies to implement, whereas a tax exemption "
            "would give more back as thanks for their service",
        ),
    ),
    MultiClaimCase(
        petition_id="310878",
        text=(
            "For those newly self employed (18 months or less) who don’t have a full 2019 Self "
            "Employed tax return to calculate a figure of financial aid from, we request that "
            "they be allowed to submit their 2020 return as evidence and be guaranteed the same "
            "level of help as other self employed people. The Government announced on 26/03/20 a "
            "package of financial support for many self employed people. Whilst a great start, it "
            "doesn’t yet go far enough. Many people became self employed during the past 18 "
            "months, and are mostly ineligible for this help. It seems catastrophically unjust "
            "that someone who has worked hard and earned money in self employment for up to 18 "
            "months is currently not eligible for anything other than Universal Credit. This is "
            "desperate. People need help and assurance now."
        ),
        demand=(
            "Financially Support Newly Self Employed People Using Upcoming 2020 Tax Returns"
        ),
        conceded=(
            "Whilst a great start, it doesn\\u2019t yet go far enough."
        ),
        claims=(
            "Newly self-employed people (18 months or less) should be allowed to submit their "
            "2020 return as evidence and be guaranteed the same financial aid as other "
            "self-employed people",
            "The Government announced a package of financial support for many self-employed "
            "people on 26/03/20",
            "The Government's package is a great start but doesn't go far enough",
            "Many people became self-employed in the past 18 months and are mostly ineligible for "
            "this help",
            "It is catastrophically unjust that someone who has worked hard and earned money in "
            "self-employment for up to 18 months is eligible for nothing other than Universal "
            "Credit",
            "People need help and assurance now",
        ),
    ),
    MultiClaimCase(
        petition_id="700317",
        text=(
            "The Government’s TB Eradication Strategy allows the continued killing of badgers, a "
            "protected species, until the end of this Parliament, despite the Labour manifesto "
            "calling the cull “ineffective.” We believe the badger cull is unjustified and must "
            "end. Some research has suggested culling results in a reduction in bovine TB (bTB) "
            "in cattle. However, there are concerns about the methodology used. Other research, "
            "which has been peer reviewed and published, shows no evidence that culling badgers "
            "reduces confirmed bTB in cattle. Over 230,000 badgers — many healthy — have been "
            "killed, disrupting ecosystems without solid scientific justification. We call for an "
            "immediate end to the cull and the implementation of cattle focused measures to "
            "control bTB, rather than what we see as scapegoating wildlife."
        ),
        demand=(
            "End the Badger cull and adopt other approaches to bovine TB control"
        ),
        conceded=(
            "Some research has suggested culling results in a reduction in bovine TB (bTB) in "
            "cattle."
        ),
        claims=(
            "The Government's TB Eradication Strategy allows continued badger killing until the "
            "end of this Parliament, despite Labour's manifesto calling the cull ineffective",
            "The badger cull is unjustified and must end",
            "Some research suggests culling reduces bovine TB in cattle, but there are concerns "
            "about its methodology",
            "Peer-reviewed, published research shows no evidence that culling badgers reduces "
            "confirmed bTB in cattle",
            "Over 230,000 badgers, many healthy, have been killed, disrupting ecosystems without "
            "solid scientific justification",
            "Cattle-focused measures should be used to control bTB instead of scapegoating "
            "wildlife",
        ),
    ),
    MultiClaimCase(
        petition_id="700540",
        text=(
            "Put restrictions on holiday companies so that they are unable to raise prices of "
            "holidays so much during school holiday times. We think the government are rightly "
            "trying to reduce the amount of time that children are removed from school for family "
            "holidays. However, we believe families have no choice as they simply cannot afford "
            "to go in holiday times due to companies raising prices significantly! By companies "
            "raising prices, and government raising fines, we think it’s becoming harder for "
            "families to afford holidays, which in turn could have a hugely negative impact on "
            "the travel industry as a whole."
        ),
        demand=(
            "Ban holiday companies raising prices in school holidays."
        ),
        conceded=(
            "We think the government are rightly trying to reduce the amount of time that "
            "children are removed from school for family holidays."
        ),
        claims=(
            "Holiday companies should be restricted from raising prices so much during school "
            "holiday times",
            "The government is rightly trying to reduce the time children are removed from school "
            "for family holidays",
            "Families have no choice but to take holidays in term time because they cannot afford "
            "holiday-time prices",
            "Price rises by companies combined with higher government fines make holidays harder "
            "for families to afford",
            "Reduced affordability could have a hugely negative impact on the travel industry as "
            "a whole",
        ),
    ),
    MultiClaimCase(
        petition_id="725515",
        text=(
            "We want the government to give trans people legal access to single-sex spaces of "
            "their acquired gender. We feel that the recent supreme court ruling could undermine "
            "trans people's access to single-sex spaces and make them vulnerable. Whilst some "
            "female only spaces may need to be protected, we think the government could legislate "
            "in a way that is more circumstantial and fair to everyone. We are concerned that "
            "post-op trans women could be forced into men's changing rooms and post-testosterone "
            "trans men could be forced to use women's bathrooms. The Gender Recognition Act "
            "(2004) enables people to legally change their gender. The Equality Act (2010) "
            "prevents discrimination on the basis of gender reassignment. We think our laws "
            "should draw a healthy balance between all parties. We are concerned that the recent "
            "supreme court ruling could leave trans people with no alternative spaces to use."
        ),
        demand=(
            "Give trans people legal access to single-sex spaces of their acquired gender"
        ),
        conceded=(
            "Whilst some female only spaces may need to be protected, we think the government "
            "could legislate in a way that is more circumstantial and fair to everyone."
        ),
        claims=(
            "The government should give trans people legal access to single-sex spaces of their "
            "acquired gender",
            "The recent supreme court ruling could undermine trans people's access to single-sex "
            "spaces and make them vulnerable",
            "Some female-only spaces may need to be protected",
            "The government could legislate in a way that is more circumstantial and fair to "
            "everyone",
            "Post-op trans women could be forced into men's changing rooms and post-testosterone "
            "trans men into women's bathrooms",
            "The Gender Recognition Act (2004) enables people to legally change their gender",
            "The Equality Act (2010) prevents discrimination on the basis of gender reassignment",
            "Laws should draw a healthy balance between all parties",
            "The ruling could leave trans people with no alternative spaces to use",
        ),
    ),
    MultiClaimCase(
        petition_id="735371",
        text=(
            "Urgently review the current approach to shared care agreements (SCAs) in England. We "
            "think a review could help ensure all SCAs are reviewed individually and fairly and "
            "not refused. We want better integration of privately diagnosed patients into NHS "
            "pathways, and continuity of care. SCAs can be declined at a GP's discretion. "
            "However, we are concerned about reports that GPs in some areas are being advised to "
            "decline SCAs in all instances. This can lead many people to pay costs we feel are "
            "exorbitant or to abandon potentially vital medication. We think this can undermine "
            "NHS goals, and can exacerbate financial strain for those with untreated ADHD. We "
            "believe urgent intervention is needed to help protect patient health and help ensure "
            "more equitable access to care."
        ),
        demand=(
            "Urgently review NHS approach to shared care agreements for ADHD"
        ),
        conceded=(
            "SCAs can be declined at a GP's discretion. However, we are concerned about reports "
            "that GPs in some areas are being advised to decline SCAs in all instances."
        ),
        claims=(
            "The current approach to shared care agreements in England should be urgently "
            "reviewed",
            "A review could ensure all SCAs are assessed individually and fairly rather than "
            "refused",
            "Privately diagnosed patients should be better integrated into NHS pathways with "
            "continuity of care",
            "GPs can decline SCAs at their discretion",
            "Reports suggest GPs in some areas are being advised to decline all SCAs",
            "Blanket refusal leads many people to pay exorbitant costs or abandon potentially "
            "vital medication",
            "This can undermine NHS goals and worsen financial strain for people with untreated "
            "ADHD",
            "Urgent intervention is needed to protect patient health and ensure more equitable "
            "access to care",
        ),
    ),
    MultiClaimCase(
        petition_id="752016",
        text=(
            "Introduce a Minister, with their own team and department, focused on the mental "
            "wellbeing of young adults in the UK, decreasing indices such as suicide and "
            "self-harm rates, and increasing the overall optimism amongst the youth of this "
            "country. With suicide being one of the leading causes of death amongst young adults "
            "in the UK, we feel as though there is not a strong enough support system for those "
            "suffering from anxiety, depression, poor mental health and more. Although there is "
            "already a Minister for Children, Families and Wellbeing, we believe that this "
            "neglects those over the age of 18, which we feel leaves a gap in the governmental "
            "acknowledgment of widespread cynicism in young adults - the future of this country."
        ),
        demand=(
            "Introduce a Minister of Mental Wellbeing for Young Adults"
        ),
        conceded=(
            "Although there is already a Minister for Children, Families and Wellbeing, we "
            "believe that this neglects those over the age of 18"
        ),
        claims=(
            "A Minister with their own team and department should be introduced to focus on the "
            "mental wellbeing of young adults in the UK, reducing suicide and self-harm and "
            "increasing youth optimism",
            "Suicide is one of the leading causes of death among young adults in the UK",
            "There is not a strong enough support system for those suffering from anxiety, "
            "depression, poor mental health and more",
            "The existing Minister for Children, Families and Wellbeing neglects those over 18",
            "This leaves a gap in governmental acknowledgment of widespread cynicism among young "
            "adults, the future of the country",
        ),
    ),
    MultiClaimCase(
        petition_id="763504",
        text=(
            "The UK suspended Sudanese study visas citing a surge in asylum claims. However, we "
            "believe most students are genuine and law-abiding. We think this blanket ban denies "
            "education, punishes lawful students, and disrupts futures. Parliament must reinstate "
            "visas and protect students’ right to study. The Home Office imposed a visa brake "
            "after student asylum claims surged 470% between 2021 2025. Although intended to "
            "prevent misuse, we think this measure punishes the majority of lawful students, "
            "blocks safe education, harms academic and professional futures, and raises serious "
            "human rights concerns. Parliament must reinstate study visas and introduce targeted "
            "safeguards to prevent abuse without restricting genuine students."
        ),
        demand=(
            "Reinstate study visas for Sudanese students and fully protect their education"
        ),
        conceded=(
            "Although intended to prevent misuse, we think this measure punishes the majority of "
            "lawful students"
        ),
        claims=(
            "The UK suspended Sudanese study visas, citing a surge in asylum claims (a 470% rise "
            "in student asylum claims between 2021 and 2025)",
            "Most Sudanese students are genuine and law-abiding",
            "The blanket visa ban punishes lawful students, denies education, and disrupts "
            "academic and professional futures",
            "The ban raises serious human rights concerns",
            "Parliament must reinstate study visas and introduce targeted safeguards against "
            "abuse without restricting genuine students",
        ),
    ),
    MultiClaimCase(
        petition_id="767458",
        text=(
            "Set the legal age of consent at 18. Allow a “close-in-age” or “peer” exception: "
            "16–17 year olds can consent only with other 16–17 year olds. Make it illegal for any "
            "adult (18+) to engage in sexual activity with someone under 18, unless they had an "
            "existing sexual relationship from age 16/17. This proposal is about safeguarding, "
            "not restriction. Teenagers form peer relationships, but there is a clear difference "
            "between these and those involving adults. We believe that raising the age of consent "
            "to 18, with a close-in-age/peer exception, would better protect young people from "
            "exploitation while respecting development. We believe that at 16 individuals are "
            "still maturing and should not be considered able to consent to sex with adults, not "
            "only those in positions of trust."
        ),
        demand=(
            "Raise the age of consent to 18 with peer exception for 16-17 year olds"
        ),
        conceded=(
            "Teenagers form peer relationships, but there is a clear difference between these and "
            "those involving adults."
        ),
        claims=(
            "The legal age of consent should be set at 18",
            "A close-in-age/peer exception should let 16-17 year olds consent only with other "
            "16-17 year olds",
            "Adults (18+) should be barred from sexual activity with under-18s, unless an "
            "existing relationship began at 16/17",
            "The proposal is about safeguarding, not restriction",
            "Teenagers form peer relationships, which clearly differ from relationships involving "
            "adults",
            "Raising the age of consent to 18 with a peer exception would better protect young "
            "people from exploitation while respecting development",
            "At 16 individuals are still maturing and should not be able to consent to sex with "
            "adults, not only those in positions of trust",
        ),
    ),
    MultiClaimCase(
        petition_id="767814",
        text=(
            "Remove the matchability score from the national transplant criteria and introduce a "
            "3 tier approach rather than 2 tier. Tier A - 100CRF and 7plus years waiting, Tier B "
            "- Once you move past the average 2.5/3 year wait, Tier C everyone else We believe "
            "the current 2 tier approach is not fit for purspose. We understand that there should "
            "be a tier A to support those with extreme situations such as 100CRF and 7plus years "
            "waiting, but currently with the matchability score which is where anyone on the list "
            "is run against a donor pool of the last 10000 donors and given a matchability score. "
            "If you are given a 10 you are moved to tier A the higher the number you get the more "
            "points you are given. 10000 equates to 0.018% roughly of the population."
        ),
        demand=(
            "Reform the National Kidney Transplant List and Remove the Matchability Score"
        ),
        conceded=(
            "We understand that there should be a tier A to support those with extreme situations "
            "such as 100CRF and 7plus years waiting, but currently with the matchability score"
        ),
        claims=(
            "The matchability score should be removed from the national transplant criteria",
            "A 3 tier approach should replace the current 2 tier approach",
            "Tier A should be for those with 100CRF and 7plus years waiting, Tier B for those "
            "past the average 2.5/3 year wait, and Tier C for everyone else",
            "The current 2 tier approach is not fit for purpose",
            "A tier A is warranted for extreme situations such as 100CRF and 7plus years waiting",
            "The matchability score runs each listed person against a donor pool of the last "
            "10000 donors, moves a score of 10 to tier A, and gives more points for higher "
            "numbers",
            "10000 donors equates to roughly 0.018% of the population",
        ),
    ),
    MultiClaimCase(
        petition_id="769174",
        text=(
            "The Government should require ICBs to offer IVF to couples, including those who have "
            "children from previous relationships. I want to express my concern and distress that "
            "some ICBs who offer IVF, do not let couples who have previous children access it, "
            "even if the child is from a past relationship. I think it is unfair that some people "
            "who do not have children of their own are being denied the opportunity to experience "
            "pregnancy and motherhood due to factors entirely outside of their control. While I "
            "understand that eligibility criteria exist, this fails to recognise individual "
            "circumstances. One partner’s previous parenthood does not change the others’ medical "
            "need for fertility treatment, nor does it lessen the emotional impact of infertility "
            "on someone as an individual."
        ),
        demand=(
            "Require ICBs to offer IVF including couples with children from past relationship"
        ),
        conceded=(
            "While I understand that eligibility criteria exist, this fails to recognise "
            "individual circumstances."
        ),
        claims=(
            "The Government should require ICBs to offer IVF to couples, including those with "
            "children from previous relationships",
            "Some ICBs that offer IVF refuse couples where one partner has a child from a past "
            "relationship (writer's concern and distress)",
            "It is unfair that people with no children of their own are denied the chance to "
            "experience pregnancy and motherhood due to factors outside their control",
            "Eligibility criteria fail to recognise individual circumstances",
            "One partner's previous parenthood does not change the other partner's medical need "
            "for fertility treatment",
            "One partner's previous parenthood does not lessen the emotional impact of "
            "infertility on the other partner as an individual",
        ),
    ),
    MultiClaimCase(
        petition_id="771145",
        text=(
            "Gilbert’s Syndrome is classified as a harmless condition, however we are concerned "
            "that some patients are experiencing debilitating symptoms that are dismissed. We "
            "want the government to fund more research into this condition and its symptoms, "
            "which could inform clinical guidelines. Gilbert’s Syndrome is a genetic liver "
            "condition causing high bilirubin levels. Whilst current NHS guidelines claim it "
            "requires no treatment or monitoring, some patients report symptoms such as fatigue, "
            "brain fog, nausea, abdominal pain and poor appetite. New UK research studying 1.8 "
            "million patients found that abdominal pain and fatigue were more common in people "
            "with Gilbert’s syndrome compared to control patients up to five years before "
            "diagnosis."
        ),
        demand=(
            "Fund research on the symptoms of Gilbert’s Syndrome"
        ),
        conceded=(
            "Gilbert's Syndrome is classified as a harmless condition, however we are concerned "
            "that some patients are experiencing debilitating symptoms that are dismissed."
        ),
        claims=(
            "Gilbert's Syndrome is classified as harmless, but some patients have debilitating "
            "symptoms that are dismissed",
            "The government should fund more research into the condition and its symptoms, which "
            "could inform clinical guidelines",
            "Gilbert's Syndrome is a genetic liver condition causing high bilirubin levels",
            "Current NHS guidelines say it requires no treatment or monitoring, yet some patients "
            "report fatigue, brain fog, nausea, abdominal pain and poor appetite",
            "New UK research on 1.8 million patients found abdominal pain and fatigue were more "
            "common in people with Gilbert's syndrome than controls up to five years before "
            "diagnosis",
        ),
    ),
    MultiClaimCase(
        petition_id="771873",
        text=(
            "Review standard university degree lengths and support better access to 2 year "
            "degrees where students can achieve the same qualification and learning outcomes "
            "without reducing standards. Many countries deliver equivalent qualifications in that "
            "time, and some UK universities already offer accelerated 2 year degrees This "
            "petition is not calling for all university degrees to be shortened. Many courses, "
            "particularly those involving placements, laboratory work or clinical training, "
            "require 3 years or longer. However, where the same qualification and learning "
            "outcomes can be achieved through more intensive study, we believe students should "
            "have the option to complete their degree in 2 years as this could reduce student "
            "debt, lower costs and help graduates enter the workforce sooner without reducing "
            "academic standards."
        ),
        demand=(
            "Review standard degree lengths and increase support for two-year degrees"
        ),
        conceded=(
            "Many courses, particularly those involving placements, laboratory work or clinical "
            "training, require 3 years or longer."
        ),
        claims=(
            "Standard university degree lengths should be reviewed",
            "Access to 2 year degrees should be improved where the same qualification and "
            "learning outcomes can be achieved without reducing standards",
            "Many countries deliver equivalent qualifications in 2 years",
            "Some UK universities already offer accelerated 2 year degrees",
            "The petition is not calling for all degrees to be shortened",
            "Many courses (placements, lab work, clinical training) require 3 years or longer",
            "Students should have the option of a 2 year degree where outcomes can be met through "
            "more intensive study",
            "2 year degrees could reduce student debt, lower costs and help graduates enter the "
            "workforce sooner",
        ),
    ),
    MultiClaimCase(
        petition_id="773972",
        text=(
            "I would ask the UK Government to require driving license holders, upon reaching 65 "
            "years old, to retake the hazard perception section of the driving theory test. They "
            "would then continue to be re-tested every 5 years. Some previous proposals can be "
            "seen as a bit much, and slightly discriminatory. However, the hazard perception "
            "section of the driving theory test is the best and most simple way to ascertain if a "
            "driver should be on the road. If someone is incapable of reacting to hazards on the "
            "road, they are a danger to everyone, from drivers to cyclists and pedestrians. I "
            "believe this simple change would have a larger impact on the safety of all of us. "
            "Thank you for reading this."
        ),
        demand=(
            "Require over 65s to retake the hazard perception test every five years"
        ),
        conceded=(
            "Some previous proposals can be seen as a bit much, and slightly discriminatory."
        ),
        claims=(
            "UK drivers should retake the hazard perception test at 65 and every 5 years after",
            "Some previous proposals are a bit much and slightly discriminatory",
            "The hazard perception test is the best and simplest way to determine whether a "
            "driver should be on the road",
            "Drivers who cannot react to hazards endanger drivers, cyclists and pedestrians",
            "This change would significantly improve safety for everyone",
        ),
    ),
    MultiClaimCase(
        petition_id="775117",
        text=(
            "We believe greyhounds deserve protection, not exploitation for profit. Greyhound "
            "racing causes injuries and deaths to dogs every year. Wales has committed to banning "
            "the sport and Scotland is ending it. We believe England should follow their lead and "
            "put animal welfare first by introducing a ban on greyhound racing. Greyhound racing "
            "continues to cause injuries and deaths to dogs in England each year. Although "
            "welfare measures have been introduced, serious concerns remain about the treatment "
            "of racing greyhounds and their quality of life. Wales has announced plans to ban "
            "greyhound racing, and Scotland is moving towards ending the sport. We believe "
            "England should follow suit by introducing legislation to ban greyhound racing and "
            "prioritise animal welfare over commercial interests."
        ),
        demand=(
            "Ban greyhound racing in England"
        ),
        conceded=(
            "Although welfare measures have been introduced, serious concerns remain about the "
            "treatment of racing greyhounds and their quality of life."
        ),
        claims=(
            "Greyhounds deserve protection, not exploitation for profit",
            "Greyhound racing causes injuries and deaths to dogs in England each year",
            "Welfare measures have been introduced but serious concerns remain about racing "
            "greyhounds' treatment and quality of life",
            "Wales has committed to banning greyhound racing and Scotland is ending it",
            "England should follow Wales and Scotland and ban greyhound racing, putting animal "
            "welfare over commercial interests",
        ),
    ),
    MultiClaimCase(
        petition_id="781121",
        text=(
            "Airports should have at least one facility which holds food that can safely cater to "
            "people who have medical dietary requirements related to the 14 main "
            "allergens.Travelling can be long and exhausting,it’s worse when you have to worry "
            "about whether you can safely eat, meaning some can’t eat at all. When you are in an "
            "airport, you will find that there are a variety of food options. However, having a "
            "food related medical condition often means you cannot consider any of these options. "
            "There are still risks with cross contamination which is still enough for someone to "
            "become incredibly ill. By ensuring there is one station which holds allergen "
            "friendly food, it ensures that more people are able to eat properly and aren’t left "
            "with the option to make themselves poorly, or to not eat at all."
        ),
        demand=(
            "To legally ensure that allergen-friendly food is always available in airports"
        ),
        conceded=(
            "When you are in an airport, you will find that there are a variety of food options."
        ),
        claims=(
            "Airports should have at least one facility holding food that is safe for people with "
            "medical dietary requirements related to the 14 main allergens",
            "Travelling is long and exhausting, and worrying about safe food makes it worse, so "
            "some people can't eat at all",
            "Airports offer a variety of food options, but people with food-related medical "
            "conditions often cannot consider any of them",
            "Cross contamination risks remain and are enough to make someone incredibly ill",
            "One allergen-friendly station would let more people eat properly without making "
            "themselves ill or going without food",
        ),
    ),
    MultiClaimCase(
        petition_id="304089",
        text=(
            "Issue an immediate and direct UK wide closure order to all theatres, music venues, "
            "pubs, nightclubs and other entertainment spaces considered to be a mass gathering "
            "space as defined by the government. Entertainment spaces across the UK are not "
            "currently entitled to any claim covering revenue lost throughout the Covid-19 "
            "crisis. This is because the current directive is only a recommendation to the "
            "public, which whilst remaining solely as a recommendation is not covered for loss of "
            "earnings by insurance. Tens of thousands of people working within these sectors are "
            "now at significant risk of the industry financially collapsing without immediate "
            "government intervention to rectify this."
        ),
        demand=(
            "Immediate UK government ordered closure for all entertainment and social spaces"
        ),
        conceded=None,
        claims=(
            "The government should issue an immediate UK-wide closure order for theatres, music "
            "venues, pubs, nightclubs and other mass gathering entertainment spaces",
            "Entertainment spaces are currently not entitled to any claim for revenue lost during "
            "the Covid-19 crisis",
            "The current directive is only a recommendation, and a mere recommendation is not "
            "covered for loss of earnings by insurance",
            "Tens of thousands of workers in these sectors are at significant risk of the "
            "industry financially collapsing without immediate government intervention",
        ),
    ),
    MultiClaimCase(
        petition_id="305758",
        text=(
            "The government has stated that cleaners, caretakers and concierges play an important "
            "role in keeping people in their buildings protected and are the frontline in the "
            "battle against coronavirus. We want key worker status so they can continue to work "
            "and have childcare in place through the schools. By providing this status, cleaning "
            "staff can ensure that there is childcare in place so they can continue to provide "
            "essential services. Cleaning is needed in hospitals, prisons, care homes, offices, "
            "retail and in homes and with many cleaners now having no childcare options it is "
            "restricting the amount of staff available. Whilst cleaners provide a vital service "
            "at all times, we believe that this status is critical during the COVID-19 pandemic."
        ),
        demand=(
            "Include cleaning, caretaker and concierge staff in the key worker group category"
        ),
        conceded=None,
        claims=(
            "The government has said cleaners, caretakers and concierges play an important role "
            "protecting people in buildings and are the frontline against coronavirus",
            "Cleaners, caretakers and concierges should be given key worker status so they can "
            "keep working and access school childcare",
            "Key worker status would let cleaning staff arrange childcare and so continue "
            "providing essential services",
            "Cleaning is needed across hospitals, prisons, care homes, offices, retail and homes, "
            "and lack of childcare is restricting available staff",
            "Cleaners provide a vital service at all times, but this status is critical during "
            "the COVID-19 pandemic",
        ),
    ),
    MultiClaimCase(
        petition_id="306034",
        text=(
            "We want the government or parliament to get all university that has closed due to "
            "COVID-19 pay back the last term accommodation fee to students as they have gone home "
            "due to the virus. The reason why we want this to happen is because it is much safer "
            "to be at home where there is food and medicine from your parents, incase we get the "
            "virus, in addition as university student we don’t have a lot of money to stay "
            "stocked up while everyone is bulk buying and there is nothing left. Furthermore some "
            "students will have to pay rent back at home while the university rent too while we "
            "are not staying there and the accommodation isn’t being used which isn’t fair as "
            "this is for our own health and well-being."
        ),
        demand=(
            "Get university to reimburse students accommodation fee for the last term"
        ),
        conceded=None,
        claims=(
            "The government or parliament should make closed universities refund last term's "
            "accommodation fees to students",
            "Students went home because of COVID-19",
            "It is safer at home, where parents provide food and medicine in case of infection",
            "University students lack money to stay stocked up while others bulk-buy and shelves "
            "are empty",
            "Some students must pay rent at home while the university also charges rent for "
            "unused accommodation",
            "Paying for unused accommodation is unfair because leaving was for their health and "
            "well-being",
        ),
    ),
    MultiClaimCase(
        petition_id="306199",
        text=(
            "NHS nurses do not have the same rights to strike, they get paid considerably less "
            "than, and yet they spend the same amount of time training and even more time and "
            "money in renewing and registering than teachers do. As a result NHS nurses should be "
            "remunerated at least in line with teachers. Whilst NHS nurses are encouraged to pay "
            "into a union, unlike teachers they have no right to strike. In times such as the "
            "Covid-19 outbreak, schools are closed and teachers can safely isolate themselves but "
            "nurses cannot and are infact expected to work more shifts and longer hours. If a "
            "school pupil physically or verbally attacks a teacher, the pupil will be removed "
            "from school. If a patient or patients relative physically or verbally attacks a "
            "nurse, the patient still has the right to treatment."
        ),
        demand=(
            "Give NHS nurses the same pay and rights as school teachers"
        ),
        conceded=None,
        claims=(
            "NHS nurses lack the same strike rights as teachers",
            "Nurses are paid considerably less than teachers",
            "Nurses train for the same time as teachers and spend more time and money on renewing "
            "and registering",
            "Nurses should be paid at least in line with teachers",
            "Nurses are encouraged to join a union but have no right to strike, unlike teachers",
            "During Covid-19 teachers can safely isolate while nurses cannot and are expected to "
            "work more shifts and longer hours",
            "A pupil who attacks a teacher is removed from school, but a patient who attacks a "
            "nurse still has the right to treatment",
        ),
    ),
    MultiClaimCase(
        petition_id="306368",
        text=(
            "After covid 19, all children to return to there school classes for a minimum of 4 "
            "weeks and have time to see there friends and say goodbye. This is especially "
            "important for years 6 and 11 who will be moving on to other schools and education "
            "providers. Make sure our children get the normal adjustment time before educational "
            "transition. Especially children in year 6 and year 11. Not only will these children "
            "miss out on there exams but many will be missing school trips, camps, graduation "
            "days and proms. These are the things you take forward and remember for years to "
            "come. If school changes happen without transition time this could have a huge impact "
            "on many children and especially those children with additional needs."
        ),
        demand=(
            "Children to have time back at school after covid19."
        ),
        conceded=None,
        claims=(
            "After covid 19, all children should return to their school classes for a minimum of "
            "4 weeks to see friends and say goodbye",
            "This is especially important for years 6 and 11, who are moving on to other schools "
            "and education providers",
            "Children should get the normal adjustment time before educational transition",
            "Years 6 and 11 will miss exams, school trips, camps, graduation days and proms, "
            "which are memories carried for years",
            "School changes without transition time could have a huge impact on many children, "
            "especially those with additional needs",
        ),
    ),
    MultiClaimCase(
        petition_id="306716",
        text=(
            "Over 2 Million Self Employed people, lost their income and business instantly. "
            "People are being asked to isolate whilst going bankrupt. Self Employed Workers "
            "(according to the logic behind IR35) should be in the same position with regards tax "
            "to Employees so why not now? We have been awarded £94.25 per week, which is "
            "impossible to live on for most people. This will mean families go hungry, and homes "
            "will be in jeopardy (in the long run) and escalating debts for the self employed. "
            "Its inhumane and Self Employed workers/Freelancers will struggle to meet your "
            "lockdown requirements with no or little money."
        ),
        demand=(
            "Offer 80% lost income to self employed to a max of £2500 per month."
        ),
        conceded=None,
        claims=(
            "Over 2 million self-employed people lost their income and businesses instantly",
            "People are being asked to isolate while going bankrupt",
            "By the logic of IR35, self-employed workers should be treated like employees for tax "
            "purposes, so they should get equivalent support now",
            "The self-employed have been awarded only £94.25 per week, which is impossible to "
            "live on",
            "This will cause families to go hungry, put homes in jeopardy, and escalate debts",
            "The situation is inhumane",
            "Self-employed workers and freelancers will struggle to meet lockdown requirements "
            "with little or no money",
        ),
    ),
    MultiClaimCase(
        petition_id="306781",
        text=(
            "I am asking the Government to enforce a temporary ban on trading for non-essential "
            "retailers, such as clothing shops, during the Coronavirus epidemic. This is to "
            "ensure workers are protected from becoming ill or infecting others. These workers "
            "should be paid for their time off and keep their jobs. Retail workers potentially "
            "come into contact with hundreds of customers each day. Therefore, the risk of these "
            "employees contracting, carrying or spreading Coronavirus is high. Keeping "
            "non-essential stores open is not only dangerous to them but to their families. Those "
            "still going into work are scared to do so in a time where collective mental health "
            "is already at a low. Do the right thing and close non-essential retail stores until "
            "the epidemic passes and ensure employees continue to be paid."
        ),
        demand=(
            "Temporarily close non-essential retail stores and ensure pay for employees"
        ),
        conceded=None,
        claims=(
            "The Government should enforce a temporary trading ban on non-essential retailers "
            "during the epidemic",
            "The ban would protect workers from becoming ill or infecting others",
            "Workers should be paid for their time off and keep their jobs",
            "Retail workers come into contact with hundreds of customers daily",
            "The risk of these employees contracting, carrying or spreading Coronavirus is high",
            "Keeping non-essential stores open endangers workers and their families",
            "Workers still going in are scared, at a time when collective mental health is "
            "already low",
        ),
    ),
    MultiClaimCase(
        petition_id="306940",
        text=(
            "We the self-employed, want to be considered and supported just as those who are PAYE "
            "have been. There is no reason why we should be left behind as if we are not just as "
            "vulnerable if not more so than those who are employed. We pay taxes just like "
            "everyone else and as much we deserve a fair deal. It is now estimated that 4.8 "
            "million people in the UK are self-employed. This means the number of self-employed "
            "workers now accounts for around 15% of the working population. The chancellor has "
            "decided that employees who cannot work will receive 80% of their salary, up to "
            "£2.5k/month, however, the self-employed are offered £94 a week. This will completely "
            "destroy the businesses some of us have put our blood sweat and tears into and will "
            "have a devastating ripple effect on our families and lives."
        ),
        demand=(
            "Support the self-employed with the same support given to those on PAYE Covid19"
        ),
        conceded=None,
        claims=(
            "The self-employed want to be considered and supported just as PAYE employees have "
            "been",
            "There is no reason the self-employed should be left behind, since they are as "
            "vulnerable as or more vulnerable than employees",
            "The self-employed pay taxes like everyone else and deserve a fair deal",
            "About 4.8 million people in the UK are self-employed, around 15% of the working "
            "population",
            "The chancellor offers employees 80% of salary up to £2.5k/month but offers the "
            "self-employed only £94 a week",
            "This unequal support will destroy self-employed businesses and have a devastating "
            "ripple effect on families and lives",
        ),
    ),
    MultiClaimCase(
        petition_id="307030",
        text=(
            "Make it easier and faster for self employed sole traders to receive financial help "
            "without having to go through the benefits system. Whilst employees can claim ssp or "
            "have the backup from the government to pay a partial wage, self employed sole "
            "traders have no wage when jobs get cancelled, this is happening now. As most of them "
            "have credit accounts with there suppliers there will still be bills coming in that "
            "have to be paid, plus the tax that they have to account for for the next tax payment "
            "due. Self employed can not wait in the benefits queue while the bills are rolling in "
            "and there’s no food on the table."
        ),
        demand=(
            "Give same financial help to self employed as employees during COVID-19 crisis"
        ),
        conceded=None,
        claims=(
            "Self-employed sole traders should be able to get financial help more easily and "
            "quickly, without going through the benefits system",
            "Employees can claim SSP or get government-backed partial wages, but self-employed "
            "sole traders have no wage when jobs are cancelled",
            "This loss of work is happening now",
            "Sole traders still have supplier credit-account bills and upcoming tax payments to "
            "meet",
            "The self-employed cannot wait in the benefits queue while bills arrive and there is "
            "no food on the table",
        ),
    ),
    MultiClaimCase(
        petition_id="307053",
        text=(
            "It is a requirement now more than ever the government must implement an immediate "
            "increase in the pay scale and structure of all NHS frontline employees. All middle "
            "managers of NHS trusts should be streamlined and salaries capped. In the midsts of "
            "COVID-19 outbreak, we have been starkly reminded of the integral role the NHS plays "
            "in the U.K. The NHS has been neglected and the necessary funds withheld for decades. "
            "The NHS has begged for the publics attention for years and now in this uncertain "
            "time we the public now need the NHS and those who ensure it runs daily more than "
            "ever. It is about time we the people stand up for the people in the NHS who care for "
            "us while we prepare as one community to overcome this disease."
        ),
        demand=(
            "Implement a national salary increase of all front line NHS employees"
        ),
        conceded=None,
        claims=(
            "The government must immediately increase pay scale and structure for all NHS "
            "frontline employees",
            "NHS trust middle managers should be streamlined and their salaries capped",
            "COVID-19 has starkly reminded us of the NHS's integral role in the U.K.",
            "The NHS has been neglected and denied necessary funds for decades",
            "The NHS has begged for public attention for years and the public now needs it more "
            "than ever",
            "The public should stand up for NHS staff who care for them while uniting to overcome "
            "the disease",
        ),
    ),
    MultiClaimCase(
        petition_id="307162",
        text=(
            "I want the government to offer self employed the same financial aid they have "
            "offered people on a paye roll. statutory sick pay wont cover people's rent, bills "
            "food and insurance for work. People who rely on working in peoples houses have lost "
            "alot of work and have no idea when business will pick back up. However they are "
            "expected to survive of £94.25 a week when many will make this a day and will still "
            "struggle to pay all of the bill's. Self employed contribute to the state just as "
            "much as thoughs on paye roll. Why should the self employed be treated differently "
            "during a pandemic. Self employed couldnt prepare for the effects of a pandemic."
        ),
        demand=(
            "Give self employed the same aid as employed for the duration of coronavirus"
        ),
        conceded=None,
        claims=(
            "The government should offer self employed people the same financial aid given to "
            "people on a payroll",
            "Statutory sick pay won't cover rent, bills, food and insurance for work",
            "People who work in other people's houses have lost a lot of work and don't know when "
            "business will recover",
            "Self employed are expected to survive on £94.25 a week, which many would make in a "
            "day and still struggle to pay bills",
            "Self employed contribute to the state just as much as those on payroll",
            "Self employed should not be treated differently during a pandemic",
            "Self employed couldn't prepare for the effects of a pandemic",
        ),
    ),
    MultiClaimCase(
        petition_id="307460",
        text=(
            "Health & social care worker are some of the lowest paid staff in this country, yet "
            "they are the ones who place themselves in the front line during these unprecedented "
            "times, placing themselves at greater risk to ensure that the most vulnerable in "
            "society continue to be supported and cared for Raise the minimum wage immediately to "
            "a Minimum of £10.75 living wage for all health & social care workers, including "
            "school leavers & those under 25 years of age immediately to ensure that they can "
            "continue to support themselves and their families whilst placing themselves at risk "
            "day in day out without question"
        ),
        demand=(
            "Raise the pay for health & social care workers"
        ),
        conceded=None,
        claims=(
            "Health and social care workers are among the lowest paid staff in the country",
            "They place themselves on the front line and at greater risk during these "
            "unprecedented times to support and care for the most vulnerable",
            "The minimum wage for all health and social care workers, including school leavers "
            "and under-25s, should be raised immediately to a £10.75 living wage",
            "The raise is needed so they can support themselves and their families while risking "
            "themselves daily without question",
        ),
    ),
    MultiClaimCase(
        petition_id="307542",
        text=(
            "I would like the government to provide economic aid to self-employed who are "
            "operating as individuals or sole traders in industries that have been affected by "
            "the fallout of the Coronavirus, similar to that offered to those who are not "
            "considered \"key workers\" who are directly employed. During the current Coronavirus "
            "crisis, relief and other assistance has been offered to those who are directly "
            "employed, however, no support has been offered to people who are self employed who "
            "may or may not be eligible for Universal Credit. These individuals may struggle to "
            "make ends meet with bills and other expenses whilst they are unable to work, either "
            "through lack of work or through social distancing and self-isolation."
        ),
        demand=(
            "Equality in economic aid for the self-employed during the Coronavirus period"
        ),
        conceded=None,
        claims=(
            "The government should provide economic aid to self-employed individuals and sole "
            "traders in industries affected by Coronavirus, similar to aid for directly employed "
            "non-key workers",
            "Relief has been offered to directly employed people during the crisis but no support "
            "has been offered to the self-employed, who may or may not be eligible for Universal "
            "Credit",
            "Self-employed people may struggle to pay bills and expenses while unable to work due "
            "to lack of work, social distancing or self-isolation",
        ),
    ),
    MultiClaimCase(
        petition_id="307613",
        text=(
            "Provide life insurance cover for each NHS healthcare worker, equal to lifetime NHS "
            "earnings, in case they die, during Corona virus pandemic, with diagnosis of Corona "
            "+ve. Healthcare workers need assurance that families and loved ones will get "
            "financial stability, if they die, while saving lives Healthcare workers are putting "
            "their own lives at risk, while providing care for patients, suspected and proven "
            "cases of Corona virus. We know that there is not enough PPE equipment to use as "
            "Universal precautions, while dealing with all patients. Testing for suspected cases "
            "is limited, based on high risk symptoms, travel and contact history. This invariably "
            "means healthcare workers are at higher risk than anyone else, even if they follow "
            "all recommended measures."
        ),
        demand=(
            "Provide life insurance cover for NHS staff, risking their lives, during Covid19"
        ),
        conceded=None,
        claims=(
            "NHS healthcare workers should each be given life insurance cover equal to their "
            "lifetime NHS earnings if they die of Covid-19 during the pandemic",
            "Healthcare workers need assurance that their families will have financial stability "
            "if they die",
            "Healthcare workers are risking their lives caring for suspected and confirmed "
            "Covid-19 patients",
            "There is not enough PPE to apply universal precautions with all patients",
            "Testing of suspected cases is limited to high-risk symptoms, travel and contact "
            "history",
            "Healthcare workers are therefore at higher risk than anyone else, even if they "
            "follow all recommended measures",
        ),
    ),
    MultiClaimCase(
        petition_id="307675",
        text=(
            "For the duration of the COVID 19 crisis, those people identified as key workers "
            "should receive as close to 100% of their gross pay as possible through the "
            "reduction/suspension of tax and PAYE on their salary. Key workers are being asked to "
            "carry on working through this current crisis, risking theirs and their families "
            "health with no added reward, whilst those who are forced to stay home with loss of "
            "earnings are being subsidised 80% salary to do so. This seems grossly unfair since "
            "key workers taxes are being used during this time to subsidise the salaries of "
            "mainly private sector workers."
        ),
        demand=(
            "Make key workers exempt from tax/PAYE on salary during the COVID19 duration."
        ),
        conceded=None,
        claims=(
            "Key workers should receive close to 100% of gross pay during the COVID-19 crisis via "
            "suspension/reduction of tax and PAYE",
            "Key workers are being asked to keep working and risk their own and their families' "
            "health with no added reward",
            "Those forced to stay home with loss of earnings are subsidised at 80% of salary",
            "The arrangement is grossly unfair",
            "Key workers' taxes are being used to subsidise the salaries of mainly private sector "
            "workers",
        ),
    ),
    MultiClaimCase(
        petition_id="307710",
        text=(
            "We pay to be on a national register run by the DVSA, a government body that has "
            "closed test centres to protect examiners, as they do not deem it safe for them to be "
            "in our vehicles. However, they have failed to extend a duty of care and offer any "
            "support to is 40,000 registered driving instructors!! The revenue to be placed on "
            "the register generates £3M per year! 1.34M theory tests: £30.9M revenue (2019) 1.66M "
            "practical tests: £102.2M revenue (2019) Total: £136,191,357 Driving instructors are "
            "the cog of this organisation and that money is being fed straight into the "
            "government’s pockets. We are part of a government run compulsory register & the DVSA "
            "need to step in to protect its front line workers with a duty of care."
        ),
        demand=(
            "Force the DVSA to extend its duty of care to its UK Driving Instructors"
        ),
        conceded=None,
        claims=(
            "Instructors pay to be on a national register run by the DVSA",
            "The DVSA closed test centres to protect examiners, deeming it unsafe for them to be "
            "in instructors' vehicles",
            "The DVSA has failed to extend a duty of care or offer any support to its roughly "
            "40,000 registered instructors",
            "Placing instructors on the register generates about dollar3M per year",
            "Theory and practical tests generate large revenue ( 30.9M and 102.2M in 2019; total "
            "136,191,357)",
            "Driving instructors are the cog of the organisation and that money goes straight "
            "into the government's pockets",
            "The register is government run and compulsory, so the DVSA needs to protect its "
            "front line workers with a duty of care",
        ),
    ),
    MultiClaimCase(
        petition_id="308194",
        text=(
            "I run 4 hairdressing salons across London where myself and staff are constantly in "
            "contact with people, cutting their hair and touching their face despite the advice. "
            "We want the government to enforce all hairdressing salons and beauty to shut their "
            "doors as they have for restaurants and bars. The coronavirus is effecting my "
            "business a substantial amount. I am concerned about my staff and also my clients. I "
            "am also a 68 year old man who needs to stay inside however I cannot in order to save "
            "my business. I have been on walks during the restaurant and bar lock down and see "
            "other hair salons open, but their stylists are sitting without any clients. "
            "Therefore, I know this will be a question amongst many who wonder why salons are not "
            "facing enforced closures."
        ),
        demand=(
            "Enforce the Hairdressing and Beauty industry to close during COVID-19 outbreak."
        ),
        conceded=None,
        claims=(
            "The author runs 4 London hairdressing salons where staff are in constant close "
            "contact with clients, touching faces despite advice",
            "The government should enforce closure of all hairdressing and beauty salons, as it "
            "did for restaurants and bars",
            "Coronavirus is substantially hurting the author's business",
            "The author is concerned about staff and clients",
            "The author is 68 and needs to stay inside but cannot in order to save the business",
            "Other salons seen open on walks have stylists sitting without clients",
            "Many others likely wonder why salons are not facing enforced closures",
        ),
    ),
    MultiClaimCase(
        petition_id="308244",
        text=(
            "Government should provide all doctors, nurses and other active key workers "
            "protective gear, including suitable masks, for protection against, and reducing the "
            "spread of, COVID-19. Hospital doctors currently have no protection against COVID-19 "
            "when seeing patients during face-to-face consultations. They come back and forth "
            "between home and the the hospital, where coronavirus could unknowingly spread "
            "between patients, other doctors and their families at home. Not only are hospital "
            "doctors affected, but so are nurses, general practitioners, and other key workers "
            "that have no choice but to be within close proximity of possibly virus-infected "
            "people. Government must act now."
        ),
        demand=(
            "Provide all hospital doctors and key workers with protective equipment for COVID"
        ),
        conceded=None,
        claims=(
            "Government should provide all doctors, nurses and other active key workers with "
            "protective gear, including suitable masks, against COVID-19",
            "Hospital doctors currently have no protection against COVID-19 during face-to-face "
            "consultations",
            "Doctors travel between home and hospital, so the virus could unknowingly spread "
            "between patients, other doctors and their families",
            "Nurses, GPs and other key workers are also affected because they must be in close "
            "proximity to possibly infected people",
            "Government must act now",
        ),
    ),
)

#: The 40 with the demand stated only in the text's second half.
MULTI_CLAIM_CASES_LATE: tuple[MultiClaimCase, ...] = (
    MultiClaimCase(
        petition_id="307383",
        text=(
            "The government should help students who have been ignored in the recent fiscal "
            "packages. By calling for a rent freeze on all privately owned and university owned "
            "accomodation as well as ensuring every student receives the highest tier of loan "
            "next term regardless of parental income. The government should help students who "
            "have been ignored in the recent fiscal packages. By calling for a rent freeze on all "
            "privately owned and university owned accomodation as well as ensuring every student "
            "receives the highest tier of loan next term regardless of parental income. This is "
            "because some parents may have been laid off, facing financial difficulty and the "
            "potential to not be able to support students as the government would expect. It "
            "would also help if a lockdown occurs."
        ),
        demand=(
            "Give University Students Financial Security."
        ),
        conceded=None,
        claims=(
            "The government should help students who have been ignored in the recent fiscal "
            "packages",
            "The government should call for a rent freeze on all privately owned and university "
            "owned accommodation",
            "The government should ensure every student receives the highest tier of loan next "
            "term regardless of parental income",
            "Some parents may have been laid off and be unable to support students as the "
            "government would expect",
            "The measures would also help if a lockdown occurs",
        ),
    ),
    MultiClaimCase(
        petition_id="308512",
        text=(
            "The NHS faces being totally overwhelmed by COVID-19 in the coming days. We must buy "
            "time to fight the coronavirus. Lockdown - countrywide enforced social distancing - "
            "can prevent hundreds of thousands of deaths and allow medics, scientists, and "
            "policymakers time to learn more and respond. Millions of lives are at stake! There "
            "is hesitation to bring down the “Hammer” now because of fear the outbreak will "
            "resume as soon as we ease social distancing. But South Korea has shown that 3-8 "
            "weeks of suppression can get the virus under control. After that, it’ll be an "
            "ongoing “Dance” of testing and tracing to keep the virus from breaking out again "
            "until effective treatments and vaccinations arrive. A Hammer-and-Dance strategy is "
            "the best way to save lives and minimise economic damage."
        ),
        demand=(
            "Implement a Hammer and Dance strategy for dealing with COVID-19 Immediately"
        ),
        conceded=(
            "There is hesitation to bring down the \"Hammer\" now because of fear the outbreak will "
            "resume as soon as we ease social distancing."
        ),
        claims=(
            "The NHS faces being totally overwhelmed by COVID-19 in the coming days",
            "We must buy time to fight the coronavirus",
            "Lockdown (countrywide enforced social distancing) can prevent hundreds of thousands "
            "of deaths and give medics, scientists and policymakers time to learn and respond",
            "Millions of lives are at stake",
            "There is hesitation to impose the \"Hammer\" now out of fear the outbreak will resume "
            "once distancing eases",
            "South Korea has shown that 3-8 weeks of suppression can get the virus under control",
            "After suppression, an ongoing \"Dance\" of testing and tracing can keep the virus from "
            "breaking out again until treatments and vaccines arrive",
            "A Hammer-and-Dance strategy is the best way to save lives and minimise economic "
            "damage",
        ),
    ),
    MultiClaimCase(
        petition_id="310742",
        text=(
            "Hundreds of thousands of brave men and women are fighting an invisible war to save "
            "not only the lives of the entire population, but to save the United Kingdom from a "
            "viral enemy. This is the first time in national peacetime that war is being fought "
            "where people are putting their lives before ours. These unsung heroes are overlooked "
            "so many times doing the amazing jobs they do 24 hours a day, 365 days a year. "
            "Doctors, nurses, radiographers, porters, cleaners and many other NHS staff are going "
            "to work everyday knowing that they are putting their lives at significant risk. "
            "These brave soldiers of health were conscripted purely because of their vocation to "
            "help others. I urge the Government to create a new Queen's Medal of Courage for NHS "
            "workers who are bravely fighting on the front line."
        ),
        demand=(
            "Award the bravery of our NHS heroes fighting Coronavirus with a Medal of Courage"
        ),
        conceded=None,
        claims=(
            "Hundreds of thousands of people are fighting an invisible war to save lives and save "
            "the UK from a viral enemy",
            "This is the first time in peacetime that people are putting their lives before ours",
            "These unsung heroes are often overlooked despite working around the clock",
            "NHS staff (doctors, nurses, radiographers, porters, cleaners, etc.) go to work "
            "knowing they are putting their lives at significant risk",
            "These health workers were conscripted purely because of their vocation to help "
            "others",
            "The Government should create a new Queen's Medal of Courage for NHS workers on the "
            "front line",
        ),
    ),
    MultiClaimCase(
        petition_id="558784",
        text=(
            "Mortality from COVID-19 is a very really concern for all CEV. Many work in front "
            "line jobs where they cant work from home. Whilst many will find it hard mentally, "
            "thousands more are experiencing daming mental health through fear, stress anxiety, "
            "anguish . Without Government advice many who want/need to shield have no choice, its "
            "either shield and face financial poverty, or work and face long term health "
            "complications or even death. We ask that all 4 nation Governments provide support "
            "the CEV who cant work from home to stay at home. Shielding is a choice, however "
            "individuals right to autonomy can not be exercised without official advice from the "
            "Government to shield. We implore the Government help protect us."
        ),
        demand=(
            "Support Clinical Extremely Vulnerable to stay at home UK wide."
        ),
        conceded=None,
        claims=(
            "COVID-19 mortality is a real concern for all CEV (clinically extremely vulnerable) "
            "people",
            "Many CEV people work front line jobs and cannot work from home",
            "Thousands are suffering mental health damage from fear, stress, anxiety and anguish",
            "Without Government advice, CEV people must choose between shielding and financial "
            "poverty or working and risking health complications or death",
            "All four nation Governments should support CEV people who cannot work from home to "
            "stay at home",
            "Shielding is a choice, but autonomy cannot be exercised without official Government "
            "advice to shield",
        ),
    ),
    MultiClaimCase(
        petition_id="558910",
        text=(
            "Peadophiles need to spend way more time behind bars than they currently do. They "
            "cause the victim and the victims family so much mental damage they may never fully "
            "recover from. I know this as one of my family members was also a victim, yet the "
            "offender was let out of prison after just a few years. After seeing the video of "
            "that peadophile in Mitcham yesterday I can not understand how these vile people are "
            "allowed to wonder the streets after just a few years in prison. This needs to be "
            "seriously looked at and treated as harshly as possible these peadophiles are "
            "destroying lives. The victims are handed a life sentence of trauma yet their "
            "offenders are free to walk after a few short years. Extend the sentencing for "
            "Paedophiles keep the children safe."
        ),
        demand=(
            "Extend the Prison sentencing for Paedophiles and Child Abusers."
        ),
        conceded=None,
        claims=(
            "Paedophiles should serve much longer prison sentences",
            "Child sexual abuse causes lasting mental damage to victims and their families",
            "The author's own family member was a victim and the offender was released after a "
            "few years",
            "After seeing a video of a paedophile in Mitcham, the author can't understand why "
            "such offenders are released after a few years",
            "Sentencing needs to be seriously reviewed and made as harsh as possible",
            "Victims get a life sentence of trauma while offenders go free after short sentences",
            "Longer sentences would keep children safe",
        ),
    ),
    MultiClaimCase(
        petition_id="700047",
        text=(
            "We’re seeking reform to the punitive policy for term time leave that "
            "disproportionately impacts families that are already under immense pressure and "
            "criminalises parents that we think are making choices in the best interests of their "
            "families. No family should face criminal convictions! The data that the DfE has "
            "published are statistics based on what we consider is a very weak correlation "
            "between school attendance and attainment, but they have failed entirely to consider "
            "causation. The SEND issues have also been ignored, and we believe some children are "
            "being discriminated against due to the strict guidelines that have been put in "
            "place. Many children with SEND do have a disability, and are therefore protected "
            "under the Equality Act. We are calling for reform of legislation on taking children "
            "out of school urgently."
        ),
        demand=(
            "Allow parents to take their children out of school for up to 10 days fine free."
        ),
        conceded=None,
        claims=(
            "The term time leave policy is punitive and disproportionately impacts families "
            "already under pressure",
            "The policy criminalises parents who are making choices in their families' best "
            "interests",
            "No family should face criminal convictions",
            "The DfE's published data rest on a very weak correlation between attendance and "
            "attainment",
            "The DfE has failed to consider causation",
            "SEND issues have been ignored",
            "Some children are being discriminated against due to the strict guidelines",
            "Many children with SEND have a disability and are protected under the Equality Act",
            "Legislation on taking children out of school needs urgent reform",
        ),
    ),
    MultiClaimCase(
        petition_id="700638",
        text=(
            "We believe that many graduates, myself included, who spent £27k+ on university are "
            "struggling to find jobs. Entry-level roles often demand experience, which feels "
            "unfair, as we're constantly rejected for lacking it. We need opportunities, yet many "
            "of us lack industry connections. We want the Government to review the job "
            "opportunities available to new graduates and how graduates can get the experience "
            "necessary to do those jobs. Please help to give us a chance."
        ),
        demand=(
            "Conduct a review of routes into work for new graduates."
        ),
        conceded=None,
        claims=(
            "Many graduates, including the author, spent £27k+ on university and are struggling "
            "to find jobs",
            "Entry-level roles often demand experience, which feels unfair since graduates are "
            "rejected for lacking it",
            "Graduates need opportunities but many lack industry connections",
            "The Government should review graduate job opportunities and how graduates can gain "
            "the necessary experience",
        ),
    ),
    MultiClaimCase(
        petition_id="700671",
        text=(
            "We believe that ketamine use is a rising problem amongst the 18-30 age range, and "
            "feel that the damage it can cause to people’s bodies can be rapid and detrimental. "
            "It’s appearing that ketamine can make visible and detrimental damage to people’s "
            "bodies within a very short timeframe. We believe it needs to be brought to attention "
            "that this could be a serious problem within the local communities and people are not "
            "talking about it enough. We think that reclassifying ketamine as a class A drug "
            "could increase the information or knowledge on its potential dangers and what it can "
            "do to your body. We feel that more coverage and recognition could stop people taking "
            "it."
        ),
        demand=(
            "Reclassify Ketamine as a Class A drug"
        ),
        conceded=None,
        claims=(
            "Ketamine use is a rising problem among 18-30 year olds",
            "Ketamine can cause rapid, visible and detrimental damage to the body within a short "
            "timeframe",
            "The problem needs to be brought to attention because it may be serious in local "
            "communities and people are not talking about it enough",
            "Reclassifying ketamine as class A could increase information and knowledge about its "
            "dangers",
            "More coverage and recognition could stop people taking it",
        ),
    ),
    MultiClaimCase(
        petition_id="701342",
        text=(
            "British people are paying one of the highest prices in the world for electricity. I "
            "think that installing solar energy is destroying the British countryside, losing us "
            "productive farmland and damaging our once green and pleasant land. Where is our say "
            "in the matter? It is only fair that we, the British people, have a say on how we "
            "progress towards a greener future. That is why this petition calls for a referendum "
            "on achieving Net Zero targets. Let the people decide the path towards a sustainable "
            "future, one which we think is the best way for our taxes being spent and the "
            "countryside to be protected. Stand with us. Demand a say in our own future. Sign "
            "this petition for a referendum on our net zero goals."
        ),
        demand=(
            "Hold a referendum on achieving net zero goals."
        ),
        conceded=None,
        claims=(
            "British people pay one of the highest electricity prices in the world",
            "Solar installation is destroying the British countryside, losing productive farmland "
            "and damaging the green and pleasant land",
            "The public has no say in how the country progresses toward a greener future",
            "It is only fair that the British people have a say in how they progress toward a "
            "greener future",
            "A referendum should be held on achieving Net Zero targets",
            "The people should decide the path to a sustainable future, including how taxes are "
            "spent and how the countryside is protected",
        ),
    ),
    MultiClaimCase(
        petition_id="705131",
        text=(
            "We think the people in charge with passing laws, running the overall country "
            "interests should at least have an IQ of over 100 (country average). We think this "
            "could help make sure there is efficiency, common sense and productivity amongst the "
            "highest institution’s members. This could be a first step towards efficiency in UK. "
            "All members of Government and Parliament to be tested for IQ by third party "
            "entities. No lower than 90 (below country average) should be allowed to stand."
        ),
        demand=(
            "Introduce IQ minimum for Government and Parliament members"
        ),
        conceded=None,
        claims=(
            "People who pass laws and run the country should have an IQ of over 100 (the country "
            "average)",
            "Such a requirement would help ensure efficiency, common sense and productivity among "
            "the highest institution's members",
            "This could be a first step towards efficiency in the UK",
            "All members of Government and Parliament should be IQ-tested by third party entities",
            "No one below 90 should be allowed to stand",
        ),
    ),
    MultiClaimCase(
        petition_id="705328",
        text=(
            "I believe this law uses outdated gendered language like “his employees”, and that it "
            "should be updated to be more inclusive as it applies to everyone regardless of their "
            "gender. I believe updating this language would reflect the UK’s commitment to "
            "fairness, equality, and respect for all workers. By replacing words like “his” with "
            "“their,” I think the Government can encourage a sense of respect and belonging for "
            "all. As the Employment Rights Bill will aim to strengthen measures on sexual "
            "harassment prevention, many are shocked to see how exclusionary this language "
            "remains in the Health and Safety at Work Act. I believe updating the Act would be a "
            "meaningful step towards greater inclusivity."
        ),
        demand=(
            "Update the Health and Safety at Work Act to be gender neutral"
        ),
        conceded=None,
        claims=(
            "The law uses outdated gendered language like \"his employees\"",
            "The language should be updated to be inclusive of everyone regardless of gender",
            "Updating the language would reflect the UK's commitment to fairness, equality and "
            "respect for all workers",
            "Replacing \"his\" with \"their\" would encourage respect and belonging for all",
            "Many are shocked at how exclusionary the language in the Health and Safety at Work "
            "Act remains, given the Employment Rights Bill's aims on sexual harassment prevention",
            "Updating the Act would be a meaningful step towards greater inclusivity",
        ),
    ),
    MultiClaimCase(
        petition_id="715344",
        text=(
            "We want the Government to ensure: 1. Regulation and licensing for keepers and "
            "breeders 2. Protection of native wildlife and rescue operations 3. Introduction of "
            "new standards for care and enclosures 4. Regulation of wild fox rescues. We feel "
            "that current legislation under the Animal Welfare Act fails to address the specific "
            "needs of both native and non-native foxes. We believe the government should regulate "
            "fox keeping to ensure clear, well-defined standards of care."
        ),
        demand=(
            "Regulate the keeping and breeding of all foxes, both native and non-native"
        ),
        conceded=None,
        claims=(
            "Government should introduce regulation and licensing for keepers and breeders",
            "Government should protect native wildlife and support rescue operations",
            "Government should introduce new standards for care and enclosures",
            "Government should regulate wild fox rescues",
            "Current Animal Welfare Act legislation fails to address the specific needs of native "
            "and non-native foxes",
            "Government should regulate fox keeping to ensure clear, well-defined standards of "
            "care",
        ),
    ),
    MultiClaimCase(
        petition_id="716492",
        text=(
            "Currently, young people aged 18-20 can be paid less than those aged 21 and above, "
            "despite often performing the same job tasks. We think this pay disparity undervalues "
            "their contribution to the workplace while also meaning young people might struggle "
            "to cover basic living expenses. As the cost of living continues to rise, we think "
            "young people are being disproportionately impacted. Equalising the minimum wage for "
            "18-20 year olds could help young people meet their financial needs without being "
            "held back by age-based pay. It could allow them to focus more on their education and "
            "career growth, rather than struggling to cover basic living expenses."
        ),
        demand=(
            "Equalise the minimum wage for 18-20 year olds and 21+ workers"
        ),
        conceded=None,
        claims=(
            "Workers aged 18-20 can legally be paid less than those 21 and above despite doing "
            "the same tasks",
            "This pay disparity undervalues young people's workplace contribution",
            "The disparity may leave young people struggling to cover basic living expenses",
            "Rising cost of living disproportionately affects young people",
            "Equalising the minimum wage for 18-20 year olds could help them meet financial needs "
            "without age-based pay holding them back",
            "Equal pay could let young people focus on education and career growth",
        ),
    ),
    MultiClaimCase(
        petition_id="717827",
        text=(
            "I think senior citizens living close to the English, Scottish & Welsh borders are "
            "disadvantaged in how many local bus services they can use. Bus services run across "
            "borders and I think it would be easier and fairer if the bus pass covered the whole "
            "journey, and return, on all of these services. I think it would be fairer for all if "
            "these passes could simply be used on any bus service in the UK. This could increase "
            "pensioner independence and travel opportunities, especially for those living in "
            "border areas."
        ),
        demand=(
            "Negotiate UK-wide recognition of older person's bus passes"
        ),
        conceded=None,
        claims=(
            "Senior citizens near the English, Scottish and Welsh borders are disadvantaged in "
            "how many local bus services they can use",
            "Bus passes should cover the whole cross-border journey, and return, on services that "
            "run across borders",
            "Passes should be usable on any bus service in the UK",
            "This could increase pensioner independence and travel opportunities, especially in "
            "border areas",
        ),
    ),
    MultiClaimCase(
        petition_id="725655",
        text=(
            "Some families report treatment received from social workers during assessments (etc) "
            "is often punitive, blame-based, & shaped by narratives that are narrow, biased, "
            "oppressive, & lack context. We feel assessments frequently fail to reflect the full "
            "circumstances. We want an inquiry to assess if families feel practice aligns with "
            "ethical values & if practice is genuinely child & family-centred, & if families feel "
            "they are treated with dignity & respect. We want further consideration given to "
            "whether services are causing harm. Are children & families receiving the right care/ "
            "respect from social care professionals? The inquiry should consider the experiences "
            "of a broad and diverse range of parents, carers/ family types, & examine the wider "
            "social & financial impacts on families and society."
        ),
        demand=(
            "Call for a Public Inquiry into Systemic Issues in Children’s Social Care"
        ),
        conceded=None,
        claims=(
            "Some families report that social workers' treatment during assessments is often "
            "punitive, blame-based, and shaped by narrow, biased, oppressive, context-lacking "
            "narratives",
            "Assessments frequently fail to reflect families' full circumstances",
            "An inquiry should assess whether families feel practice aligns with ethical values, "
            "is genuinely child and family-centred, and treats them with dignity and respect",
            "Further consideration should be given to whether services are causing harm",
            "The inquiry should consider the experiences of a broad and diverse range of parents, "
            "carers and family types",
            "The inquiry should examine the wider social and financial impacts on families and "
            "society",
        ),
    ),
    MultiClaimCase(
        petition_id="729333",
        text=(
            "Some research has suggested that the share of the British population that is White "
            "British may be a minority by the end of this century. We believe that reasonable "
            "concerns about this are dismissed as racism. We want the government to take the "
            "following steps in response. 1. Deport any and all foreign criminals, and any family "
            "that may be with them in the UK 2. Reassess all rights to remain and/or citizenship "
            "granted since 2000 with a view to deporting any (and any UK born dependents), based "
            "on their contribution to national life or the economy 3. Full and immediate "
            "immigration freeze. 4. Full ECHR withdrawal. 5. Removal of all benefit access to any "
            "immigrants for their whole lifetime. 6. Automatically deport any immigrants who are "
            "out of work for more than 3 months."
        ),
        demand=(
            "New policies on deporting legal and illegal migrants & full ECHR withdrawal"
        ),
        conceded=None,
        claims=(
            "Research suggests White British people may be a minority of the British population "
            "by the end of this century",
            "Reasonable concerns about this demographic change are dismissed as racism",
            "The government should deport all foreign criminals and any family with them",
            "The government should reassess all rights to remain and citizenship granted since "
            "2000 with a view to deporting people (and UK-born dependents) based on contribution "
            "to national life or the economy",
            "The government should impose a full and immediate immigration freeze",
            "The UK should fully withdraw from the ECHR",
            "All immigrants should lose benefit access for their whole lifetime",
            "Immigrants out of work for more than 3 months should be automatically deported",
        ),
    ),
    MultiClaimCase(
        petition_id="730731",
        text=(
            "We are concerned that many families across the UK face homelessness, bankruptcy, and "
            "trauma after being forced from homes made unsafe by RAAC (Reinforced Autoclaved "
            "Aerated Concrete). These homeowners did nothing wrong — yet are left to shoulder the "
            "burden of institutional failure and unsafe construction practices. We believe many "
            "ex-council homeowners face bankruptcy and homelessness after RAAC was found in "
            "right-to-buy properties. We call for a national compensation fund and a public "
            "inquiry into government and council handling of RAAC. We seek laws mandating "
            "high-risk building registers, defect reporting by surveyors/solicitors, and 60-year "
            "developer liability. We believe mortgage interest should be banned on condemned "
            "homes, and first-time buyer status restored for affected owners. We want justice "
            "now."
        ),
        demand=(
            "RAAC Victim Justice – National Support Fund, New Legislation & public Inquiry"
        ),
        conceded=None,
        claims=(
            "Many UK families face homelessness, bankruptcy and trauma after being forced from "
            "RAAC-unsafe homes",
            "Affected homeowners did nothing wrong and are bearing the burden of institutional "
            "failure and unsafe construction",
            "Ex-council homeowners face bankruptcy and homelessness after RAAC was found in "
            "right-to-buy properties",
            "A national compensation fund should be created",
            "A public inquiry into government and council handling of RAAC should be held",
            "Laws should mandate high-risk building registers, defect reporting by "
            "surveyors/solicitors, and 60-year developer liability",
            "Mortgage interest should be banned on condemned homes",
            "First-time buyer status should be restored for affected owners",
        ),
    ),
    MultiClaimCase(
        petition_id="730919",
        text=(
            "There are rules about the flags that can be flown without local planning authority "
            "consent. The Rainbow Flag is already listed, subject to certain restrictions. We "
            "would like the Progress Flag & its Intersex inclusive version to be listed too, "
            "allowing organisations to demonstrate inclusiveness Many organisations would like to "
            "demonstrate that all LGBTQ+ people are both welcome and safe doing business with "
            "them and entering their establishments. Sadly, we believe current public discourse "
            "leaves non-binary and trans people uncertain of their safety when the older rainbow "
            "flag is flown. Adding both Progress Flags to the list of flags that don't require "
            "consent, alongside the rainbow flag, would allow organisations to freely choose "
            "which to display."
        ),
        demand=(
            "Add the Progress Pride Flags to the flags that don’t require permission"
        ),
        conceded=None,
        claims=(
            "Some flags can be flown without local planning authority consent, subject to rules",
            "The Rainbow Flag is already on the list of consent-free flags, with restrictions",
            "The Progress Flag and its Intersex-inclusive version should also be listed",
            "Listing them would let organisations demonstrate inclusiveness",
            "Many organisations want to show all LGBTQ+ people are welcome and safe",
            "Current public discourse leaves non-binary and trans people uncertain of their "
            "safety when the older rainbow flag is flown",
            "Adding both Progress Flags alongside the rainbow flag would let organisations freely "
            "choose which to display",
        ),
    ),
    MultiClaimCase(
        petition_id="734784",
        text=(
            "When someone writes your car off or damages your car, even if the insurance company "
            "has paperwork from the other side which proves they are to blame, they may put your "
            "car insurance up. We think this is wrong and should be made illegal. The law states "
            "that to drive a Vehicle on any of the UKs Roads you have to have Insurance. We feel "
            "car insurance is very expensive but it become unfairly expensive when insurance "
            "companies increase your car insurance after a no fault accident the following year. "
            "Many cases are settled, so they are aware whose fault it was. We need the Government "
            "to ban this practice."
        ),
        demand=(
            "Ban insurance companies increasing premiums after no fault claims"
        ),
        conceded=None,
        claims=(
            "Insurers may raise premiums after a no-fault accident even when paperwork proves the "
            "other party is to blame",
            "Raising premiums after a no-fault accident is wrong and should be made illegal",
            "The law requires insurance to drive a vehicle on UK roads",
            "Car insurance is very expensive and becomes unfairly more so when increased after a "
            "no-fault accident",
            "Many cases are settled, so insurers know whose fault it was",
            "The Government needs to ban this practice",
        ),
    ),
    MultiClaimCase(
        petition_id="735447",
        text=(
            "The conversation around cannabis in the UK has changed dramatically, and one thing "
            "is crystal clear: it's not going away. Despite current prohibition, a vast illicit "
            "market thrives, operating without any regard for public safety. Dealers don't check "
            "ID, meaning under 18s have easy access. We think that it is even more abhorrent, "
            "this illegal trade fuels a hidden underworld of modern slavery, with vulnerable "
            "individuals being trafficked and forced into dangerous and exploitative conditions "
            "in illicit cannabis grows across the UK. We think it's time for the UK to face this "
            "reality and implement a responsible, regulated cannabis market that prioritises "
            "public health, safety, and informed choice over the failing status quo, and actively "
            "works to dismantle the criminal enterprises that profit from human suffering"
        ),
        demand=(
            "Legalise Cannabis Use and Sales for Adults over 18"
        ),
        conceded=None,
        claims=(
            "The conversation around cannabis in the UK has changed dramatically and cannabis is "
            "not going away",
            "Despite prohibition a vast illicit cannabis market thrives without regard for public "
            "safety",
            "Dealers don't check ID so under 18s have easy access",
            "The illegal trade fuels modern slavery, with vulnerable people trafficked and forced "
            "to work in illicit grows",
            "The UK should implement a responsible, regulated cannabis market prioritising public "
            "health, safety and informed choice, and dismantle the criminal enterprises profiting "
            "from human suffering",
        ),
    ),
    MultiClaimCase(
        petition_id="735952",
        text=(
            "I live 30 mins from my work place that is in the city centre and the company I work "
            "for requires me to do office days. I have a toddler and need to drop him off at "
            "daycare and for that I need my car with me. Or a fast way to get to the day care in "
            "case anything happens. I can't afford parking. And nor can I afford to drive the "
            "rented electric scooters in the city where I live as I think they are very "
            "expensive. If privately owned e-scooters were legal on public roads for Category A "
            "licence holders like myself, I could have my own scooter, charge it at work, arrive "
            "fast to my house to drive the car to the daycare in case of emergency and not have "
            "to pay any clean air taxes. I think people that know how to drive a motorbike should "
            "be allowed to drive a 10 -15 kg electric scooter."
        ),
        demand=(
            "Allow personal e-scooters on public roads for holders of a Category A licence"
        ),
        conceded=None,
        claims=(
            "The author lives 30 minutes from their city-centre workplace and their company "
            "requires office days",
            "The author has a toddler to drop off at daycare and needs a car or a fast way to "
            "reach the daycare in an emergency",
            "The author can't afford parking",
            "Rented electric scooters are too expensive",
            "Privately owned e-scooters would let the author charge at work, get home fast to "
            "fetch the car in an emergency, and avoid clean air taxes",
            "Category A licence holders who can ride motorbikes should be allowed to ride a 10-15 "
            "kg electric scooter",
        ),
    ),
    MultiClaimCase(
        petition_id="737734",
        text=(
            "When people falsely accuse dogs of biting them dogs could be wrongly seized or even "
            "killed. This puts strain on dog owners, police and tax payers. We are concerned that "
            "people are making false allegations as a way of attack. False accusations can cause "
            "a lot of stress on those involved. We think people who lie about being bitten by a "
            "dog should be held accountable with a hefty fine or imprisonment."
        ),
        demand=(
            "Make it a specific criminal offence to lie about being bitten by a dog"
        ),
        conceded=None,
        claims=(
            "False accusations of dog bites can lead to dogs being wrongly seized or killed",
            "This strains dog owners, police and taxpayers",
            "People are making false allegations as a way of attacking others",
            "False accusations cause a lot of stress for those involved",
            "People who lie about being bitten by a dog should be held accountable with a hefty "
            "fine or imprisonment",
        ),
    ),
    MultiClaimCase(
        petition_id="744265",
        text=(
            "We believe too many drivers are causing issues by obstructing footpaths and have not "
            "been deterred by fines, which can cause issues for the disabled, blind, families "
            "with small children and the safety of all people. Therefore, fines need "
            "strengthening as a Deterrent. Footpaths must be for people and to ensure their "
            "safety which is paramount. Whilst we think people should be allowed to partially "
            "park on footpaths, fully blocking footpaths must not happen on the basis of safety. "
            "Increasing fines to a minimum of £150 could help deter them."
        ),
        demand=(
            "Increase Footpath Parking Obstruction Fines to £150 Minimum."
        ),
        conceded=(
            "Whilst we think people should be allowed to partially park on footpaths, fully "
            "blocking footpaths must not happen on the basis of safety."
        ),
        claims=(
            "Too many drivers obstruct footpaths and are not deterred by current fines",
            "Footpath obstruction causes problems for disabled, blind people, families with small "
            "children and general safety",
            "Fines need strengthening as a deterrent",
            "Footpaths must be for people and their safety is paramount",
            "People should be allowed to partially park on footpaths",
            "Fully blocking footpaths must not happen, on safety grounds",
            "Raising fines to a minimum of £150 could help deter drivers",
        ),
    ),
    MultiClaimCase(
        petition_id="749597",
        text=(
            "Make it a legal requirement that anyone practicing in the UK as a sonographer must "
            "have passed accredited exams and hold relevant qualifications. They must be "
            "registered with an accredited registration body and undergo regular assessments "
            "while practicing. We are concerned that anyone who purchases an ultrasound machine "
            "can call themselves a sonographer & begin practicing, without formal qualifications "
            "or oversight. In the UK, some unregulated sonographers in private clinics have "
            "failed to detect serious—& life-threatening—medical conditions, putting mothers & "
            "babies at risk. Sonography must become a legally protected, regulated profession, "
            "ensuring all sonographers meet required standards of education, competency, and "
            "professional accountability—both in private clinics & within the NHS."
        ),
        demand=(
            "Make sonographers a protected, regulated profession with qualifications & checks"
        ),
        conceded=None,
        claims=(
            "Sonographers practicing in the UK should be legally required to hold accredited "
            "qualifications",
            "Sonographers must be registered with an accredited registration body and undergo "
            "regular assessments",
            "Anyone who buys an ultrasound machine can currently call themselves a sonographer "
            "and practice without qualifications or oversight",
            "Unregulated sonographers in private UK clinics have missed serious, life-threatening "
            "conditions, endangering mothers and babies",
            "Sonography must become a legally protected, regulated profession with standards of "
            "education, competency and accountability in both private clinics and the NHS",
        ),
    ),
    MultiClaimCase(
        petition_id="750050",
        text=(
            "On July 4 2024, Sir Keir Starmer was elected as Prime Minister. Since then, his "
            "Government has introduced measures that were not included in the Labour Party's "
            "manifesto. We believe we were misled and the obfuscation has only got worse since "
            "Starmer took power. It is time for action. We believe the Government has failed to "
            "defend our borders from the small boats. We have no confidence in the way this "
            "Government has acted. Pensioners and farmers have been directly affected by policies "
            "that were not included in Labour's manifesto. Our country cannot go on like this. "
            "Dissolve Parliament and call a General Election now!"
        ),
        demand=(
            "Dissolve Parliament and call a General Election now!"
        ),
        conceded=None,
        claims=(
            "Starmer was elected Prime Minister on July 4 2024",
            "His Government has introduced measures not in Labour's manifesto",
            "The authors were misled and the obfuscation has worsened since Starmer took power",
            "The Government has failed to defend borders from the small boats",
            "The authors have no confidence in how the Government has acted",
            "Pensioners and farmers have been directly affected by policies not in the manifesto",
            "The country cannot go on like this",
        ),
    ),
    MultiClaimCase(
        petition_id="750275",
        text=(
            "We demand the relaxing of firearms law to allow law abiding citizens, with no "
            "criminal or poor mental health background that suggests they are dangerous, to "
            "protect themselves and their family against intrusion or attack. There are too many "
            "attacks on persons. We have limited legal ways of protecting ourselves, property or "
            "family against violent criminals. The criminal carrying out violent and sexual "
            "crimes often with the aid of lethal weapons against men, women and children know "
            "there is little the victim can do to protect themselves. I propose the Government "
            "relax firearm laws to allow the ownership of stun guns and tasers to all law abiding "
            "citizens over the age of 25."
        ),
        demand=(
            "Allow stun guns or tasers to be carried and used in self defence"
        ),
        conceded=None,
        claims=(
            "Firearms law should be relaxed so law-abiding citizens can protect themselves and "
            "their families",
            "Eligible citizens should have no criminal or poor mental health background "
            "suggesting danger",
            "There are too many attacks on persons",
            "People have limited legal ways to protect themselves, property or family against "
            "violent criminals",
            "Violent and sexual criminals, often armed with lethal weapons, know victims can do "
            "little to protect themselves",
            "The Government should allow all law-abiding citizens over 25 to own stun guns and "
            "tasers",
        ),
    ),
    MultiClaimCase(
        petition_id="750545",
        text=(
            "My sister Danielle died from asphyxiation during a domestic incident. She was locked "
            "in a property & died as result of being alone. There is currently no law requiring "
            "someone to take action when a life is at risk. This petition is inspired by Danielle "
            "Haggerty’s tragic death. Other countries have “duty to rescue” laws that protect "
            "vulnerable people and encourage intervention to save lives. Introducing a similar "
            "law in the UK would prevent future tragedies and ensure that anyone in immediate "
            "danger has someone legally required to try to save them so that no-one would ever be "
            "knowingly left alone to die."
        ),
        demand=(
            "Make it a crime to abandon someone in immediate danger without seeking help"
        ),
        conceded=None,
        claims=(
            "Danielle died of asphyxiation during a domestic incident",
            "She was locked in a property and died as a result of being alone",
            "The UK currently has no law requiring someone to act when a life is at risk",
            "The petition is inspired by Danielle Haggerty's death",
            "Other countries have duty-to-rescue laws that protect vulnerable people and "
            "encourage intervention",
            "A similar UK law would prevent future tragedies and ensure someone is legally "
            "required to try to save anyone in immediate danger",
        ),
    ),
    MultiClaimCase(
        petition_id="753779",
        text=(
            "The Rodenticide Stewardship Scheme (RSS) was created in 2015 to reduce wildlife "
            "being exposed to toxic anticoagulant rodenticides. Exposure has unfortunately risen, "
            "as these poisons are found in our water, birds and fish. We need urgent regulatory "
            "change to ban these products. The negative impact on wildlife of rodenticide use has "
            "been documented in research and publications by British Wildlife, Wild Justice, "
            "Springer Nature Link, Wildlife Poisoning Research UK and the RSPCA."
        ),
        demand=(
            "Ban the sale and use of rat poison due to the negative impact on wildlife"
        ),
        conceded=None,
        claims=(
            "The RSS was created in 2015 to reduce wildlife exposure to toxic anticoagulant "
            "rodenticides",
            "Exposure has risen, with these poisons found in water, birds and fish",
            "Urgent regulatory change is needed to ban these products",
            "The negative impact of rodenticide use on wildlife has been documented by several "
            "organisations and publications",
        ),
    ),
    MultiClaimCase(
        petition_id="755361",
        text=(
            "This is not anti-mother it is pro-child! This petition does not seek to remove or "
            "weaken mothers’ rights. It seeks to recognise responsible fathers equally, reduce "
            "conflict, and protect the best interests of children. Good fathers who show up from "
            "day one should not be treated as legally optional. We urge the Government to "
            "introduce legislation that automatically provides biological fathers who attend the "
            "birth with access to birth registration appointment, where paternity is undisputed."
        ),
        demand=(
            "Give father access to birth registration appointment if present at the birth"
        ),
        conceded=None,
        claims=(
            "The petition is pro-child, not anti-mother",
            "The petition does not seek to remove or weaken mothers' rights",
            "The petition seeks to recognise responsible fathers equally, reduce conflict and "
            "protect children's best interests",
            "Good fathers who show up from day one should not be treated as legally optional",
            "The Government should legislate to automatically give biological fathers who attend "
            "the birth access to the birth registration appointment, where paternity is "
            "undisputed",
        ),
    ),
    MultiClaimCase(
        petition_id="756075",
        text=(
            "On behalf of a group of councils, we ask the government to issue a clear, "
            "enforceable, evidence-based statutory framework to help businesses manage litter "
            "consistently, reduce environmental harm, and create fair and proportional "
            "responsibility, in partnership with local authorities and volunteers. Litter from "
            "food on the go is a persistent and growing problem across the UK. It can impact "
            "public spaces, fuel anti-social behaviour, and place a heavy burden on local "
            "authorities and volunteers. The Voluntary Code of Practice for Food on the Go was "
            "introduced in 2004, but as a voluntary measure, it is not enforceable. Furthermore, "
            "litter trends have evolved since its introduction. The code requires updating to "
            "reflect modern food-on-the-go littering across all business sectors."
        ),
        demand=(
            "Revise and make statutory the Voluntary Code of Practice for Food on the Go"
        ),
        conceded=None,
        claims=(
            "Government should issue a clear, enforceable, evidence-based statutory framework for "
            "businesses to manage litter, in partnership with local authorities and volunteers",
            "Litter from food on the go is a persistent and growing problem across the UK",
            "Such litter harms public spaces, fuels anti-social behaviour, and burdens local "
            "authorities and volunteers",
            "The 2004 Voluntary Code of Practice for Food on the Go is not enforceable because it "
            "is voluntary",
            "Litter trends have evolved since the code was introduced",
            "The code needs updating to reflect modern food-on-the-go littering across all "
            "business sectors",
        ),
    ),
    MultiClaimCase(
        petition_id="758621",
        text=(
            "Introduce some mandatory focus on basic world-applicable financial skills including "
            "but not limited to: long-term investment, pension planning, risks of debt and "
            "borrowing, budgeting and taxation. We do not believe teenagers are being aptly "
            "prepared for financial independence. We think the majority of 17/18 year olds coming "
            "out of the school system feel overwhelmed by the imminence of independent life. A "
            "major contributor to this feeling could be a lack of financial literacy. We are "
            "concerned that there is widespread inability to properly manage personal finances, "
            "resulting in a lack of monetary growth, often paired with overpaying for financial "
            "services. 1 in 6 UK adults have no personal savings, and only 23% hold any stock "
            "market investments. Financial education needs to improve in the school system."
        ),
        demand=(
            "Include more financial education in secondary school curriculum"
        ),
        conceded=None,
        claims=(
            "Schools should introduce mandatory focus on basic world-applicable financial skills "
            "(investment, pension planning, debt risks, budgeting, taxation)",
            "Teenagers are not being aptly prepared for financial independence",
            "Most 17/18 year olds leaving school feel overwhelmed by the imminence of independent "
            "life",
            "A lack of financial literacy could be a major contributor to that feeling",
            "There is a widespread inability to manage personal finances, leading to lack of "
            "monetary growth and overpaying for financial services",
            "1 in 6 UK adults have no personal savings and only 23% hold any stock market "
            "investments",
            "Financial education needs to improve in the school system",
        ),
    ),
    MultiClaimCase(
        petition_id="759668",
        text=(
            "We believe veterans who serve for decades deserve dignity and pension protections "
            "like some other pensions. Many don't receive death payments to help with funeral "
            "support and often pensions can’t pass to dependent adult children, leaving families "
            "insecure and reliant on charities. We feel this is out of step with some other "
            "pensions in the Civil Service, NHS, and private sector. We urge the Government to "
            "fund an automatic £10,000 funeral grant for deceased armed forces pensioners and "
            "reform rules to expand inheritance rights, so veterans can leave their remaining "
            "pensions to their dependent adult children. This could provide dignity in death, "
            "reduce charity reliance, improve fairness, and modernise rules and align military "
            "schemes with other schemes."
        ),
        demand=(
            "Fund £10,000 armed forces funeral grants & pension inheritance rules"
        ),
        conceded=None,
        claims=(
            "Veterans who serve for decades deserve dignity and pension protections like some "
            "other pensions",
            "Many armed forces pensioners don't receive death payments to help with funeral "
            "support",
            "Pensions often can't pass to dependent adult children, leaving families insecure and "
            "reliant on charities",
            "This is out of step with some other pensions in the Civil Service, NHS, and private "
            "sector",
            "The Government should fund an automatic £10,000 funeral grant for deceased armed "
            "forces pensioners and reform rules to expand inheritance rights",
            "These changes would provide dignity in death, reduce charity reliance, improve "
            "fairness, and align military schemes with other schemes",
        ),
    ),
    MultiClaimCase(
        petition_id="761976",
        text=(
            "We believe that the monarchy, in its current form, is an archaic and cynical "
            "institution, deeply entrenched in the fabric of the UK, yet seemingly more focused "
            "on preserving its wealth and position rather than representing the values of modern "
            "society. We feel a national dialogue about the monarchy's place in our society is "
            "long overdue. According to a recent survey by YouGov, a significant percentage of "
            "the population under 50 now favours abolishing the monarchy. We believe a national, "
            "binding referendum on the monarchy's constitutional role is the clearest and most "
            "democratic route to address this issue. A referendum could allow the British people "
            "to express their will, providing a mandate for transformation."
        ),
        demand=(
            "Hold a referendum on the abolition of the British Monarchy"
        ),
        conceded=None,
        claims=(
            "The monarchy in its current form is an archaic, cynical institution entrenched in "
            "the UK and more focused on preserving its wealth and position than representing "
            "modern values",
            "A national dialogue about the monarchy's place in society is long overdue",
            "A YouGov survey shows a significant share of under-50s favour abolishing the "
            "monarchy",
            "A national, binding referendum on the monarchy's constitutional role is the clearest "
            "and most democratic route",
            "A referendum would let the British people express their will and provide a mandate "
            "for transformation",
        ),
    ),
    MultiClaimCase(
        petition_id="763935",
        text=(
            "We believe the recent fire in Glasgow Union Street highlights the dangers of Vape "
            "stores. In this case there were no casualties but this resulted in a fire requiring "
            "several fire engines, and we think this could have had far more serious consequences "
            "and has impacted so many businesses. Until this fire - it had not crossed my mind "
            "the dangers of these vape stores. Where I live there are at least 3 vape stores with "
            "residential properties above them. I am concerned that if one of these were to go on "
            "fire overnight when people are sleeping and buildings are unattended the "
            "consequences could be catastrophic. I therefore call on the Government to consider "
            "new restrictions on where vape stores can be located."
        ),
        demand=(
            "Ban the sale of vapes in stores located in properties with residential units"
        ),
        conceded=None,
        claims=(
            "The recent Glasgow Union Street fire highlights the dangers of vape stores",
            "There were no casualties but the fire required several fire engines and affected "
            "many businesses",
            "The fire could have had far more serious consequences",
            "The author had not previously considered the dangers of vape stores",
            "At least 3 vape stores with residential properties above them are near where the "
            "author lives",
            "A similar fire overnight could be catastrophic",
            "The Government should consider new restrictions on where vape stores can be located",
        ),
    ),
    MultiClaimCase(
        petition_id="764767",
        text=(
            "The Crime and Policing Bill includes a clause which would mean that in respect of "
            "any law involving abortion, a woman would not commit an offence if acting in "
            "relation to her own pregnancy. We did not ask for this. It was not in any manifesto. "
            "We demand that abortion be abolished and criminalised. We believe our Society should "
            "Protect the Sacred Gift of Life especially Innocent Children In The Womb the Sick & "
            "Helpless We believe Life Is From Conception No Exceptions Until A Natural Death. We "
            "believe every Life is Worth Living & a Civilised Society offers Families Palliative "
            "Care Hope, Love, Kindness not death. We believe the Bill is a radical change to the "
            "law of our land which until now recognised that an unborn child has the Right to "
            "Life. Choose instead Adoption & Save Children’s Lives"
        ),
        demand=(
            "Ban and criminalise all abortions. Choose Adoption and Save Children’s Lives"
        ),
        conceded=None,
        claims=(
            "The Crime and Policing Bill includes a clause decriminalising abortion offences for "
            "a woman acting in relation to her own pregnancy",
            "This change was not requested and was not in any manifesto",
            "Abortion should be abolished and criminalised",
            "Society should protect life, especially unborn children, the sick and the helpless",
            "Life begins at conception and should be protected without exceptions until natural "
            "death",
            "Every life is worth living and a civilised society offers families palliative care, "
            "hope, love and kindness rather than death",
            "The Bill is a radical change to the law, which until now recognised the unborn "
            "child's right to life",
            "Adoption should be chosen instead of abortion",
        ),
    ),
    MultiClaimCase(
        petition_id="765125",
        text=(
            "We think high-stakes exams affect children’s mental health and disadvantages many "
            "pupils, especially those with SEND, and negatively impact attendance and inclusion. "
            "A review is needed. More project-based and continuous assessment could create a "
            "fairer system where all children thrive and succeed. We think if the Government is "
            "serious about SEND reform and inclusion, it must listen to lived experience which "
            "suggests that high-stakes testing and a one-size-fits-all system disadvantage pupils "
            "with SEND, and many other pupils, leading to disengagement and poor wellbeing. In "
            "our view, as assessment drives the system, SATs and GCSEs must be reviewed, and "
            "should include more coursework and continuous assessment. Reforms could improve "
            "pupil wellbeing, inclusion, attendance and engagement, and help restore a love of "
            "learning for all."
        ),
        demand=(
            "Review SATs and GCSEs to reduce exam reliance and increase inclusive assessment."
        ),
        conceded=None,
        claims=(
            "High-stakes exams harm children's mental health",
            "High-stakes exams disadvantage many pupils, especially those with SEND",
            "High-stakes exams negatively affect attendance and inclusion",
            "A review of the assessment system is needed",
            "More project-based and continuous assessment could create a fairer system where all "
            "children thrive",
            "If the Government is serious about SEND reform and inclusion, it must listen to "
            "lived experience",
            "High-stakes testing and a one-size-fits-all system disadvantage pupils with SEND and "
            "many others, leading to disengagement and poor wellbeing",
            "Because assessment drives the system, SATs and GCSEs must be reviewed and include "
            "more coursework and continuous assessment",
            "Reforms could improve wellbeing, inclusion, attendance and engagement and restore a "
            "love of learning for all",
        ),
    ),
    MultiClaimCase(
        petition_id="765203",
        text=(
            "Nearly 4,000 children are in need of medical evacuation from Gaza. We are asking "
            "only for 50 children with life-threatening conditions to be medically evacuated to "
            "the UK for medical treatment. We ask the UK Government to organise the medical "
            "evacuation of 50 children to the UK for treatment. They could be spread evenly "
            "through the regional major trauma centres, so no one area is not overburdened. "
            "Children with life threatening trauma injuries or health conditions such as acute "
            "renal failure which Gaza does not have the staff or facilities to treat should be "
            "prioritised. There are insufficient health staff in Gaza, with around 1,722 health "
            "workers reported to have been killed."
        ),
        demand=(
            "Evacuate 50 Gazan children with complex trauma injuries to the UK"
        ),
        conceded=None,
        claims=(
            "Nearly 4,000 children in Gaza need medical evacuation",
            "Only 50 children with life-threatening conditions are being requested for evacuation "
            "to the UK",
            "The UK Government should organise the medical evacuation of 50 children to the UK "
            "for treatment",
            "The children could be spread evenly across regional major trauma centres so no area "
            "is overburdened",
            "Children with life-threatening trauma injuries or conditions like acute renal "
            "failure that Gaza cannot treat should be prioritised",
            "Gaza has insufficient health staff, with around 1,722 health workers reported killed",
        ),
    ),
    MultiClaimCase(
        petition_id="767397",
        text=(
            "People purchase products en-masse (often on credit) to resell, such as trading "
            "cards, trainers and other limited edition items. For these items there can be "
            "markups of so much as 200% or more on resold products. This has become a \"viable\" "
            "means of making a living for many individuals, using the internet to sell items via "
            "post after purchasing them in person at retailers. Scalpers will use digital means "
            "to buy up product online and they also travel around shops, purchasing as much of a "
            "given item as they can and often emptying shelves before an actual consumer can "
            "reach them. This has forced hops to often implement measures to limit purchases "
            "which has in turn resulted in threats or acts of violence to staff of retailers or "
            "simple theft of \"high value\" items. I wish for the government to ban immediate "
            "(within 6 months of purchase) resale of items purchased from a seller at retail "
            "price (or equivalent) with no modification at inflated prices."
        ),
        demand=(
            "Ban 'scalping' of items for short term resale at inflated prices."
        ),
        conceded=None,
        claims=(
            "People buy products en masse, often on credit, to resell them (trading cards, "
            "trainers, limited edition items)",
            "Resale markups can reach 200% or more",
            "Scalping has become a 'viable' way for many individuals to make a living, selling "
            "online by post after buying in person",
            "Scalpers use digital means and visit shops to buy up as much stock as possible, "
            "emptying shelves before genuine consumers can reach them",
            "Shops have been forced to limit purchases, which has led to threats or violence "
            "against staff and theft of high value items",
            "The government should ban resale within 6 months of purchase of unmodified items "
            "bought at retail price and resold at inflated prices",
        ),
    ),
    MultiClaimCase(
        petition_id="769134",
        text=(
            "My wife and I are both wheelchair users when we want to go anywhere it’s impossible "
            "for us both to go by bus because many bus companies around the country will only "
            "allow one wheelchair on a bus at a time. It means that if we want to go out together "
            "we have to use a train although we have a bus pass Bus companies around the country "
            "must have only space for a wheelchair user on a bus. There are lots of couples that "
            "have to use another means of transport or travel on separate buses, this is totally "
            "unfair. My wife won’t travel on her own, so it’s impossible for us to use our bus "
            "passes together. What makes it worse is there is sometimes only one wheelchair "
            "space, but they will allow 3 pushchairs, walkers, luggage etc. We are in an age with "
            "equal rights, it’s time buses had 2 wheelchairs spaces."
        ),
        demand=(
            "Require every bus to have at least 2 spaces for wheelchairs"
        ),
        conceded=None,
        claims=(
            "Many bus companies allow only one wheelchair per bus, so the author and his wife "
            "cannot travel together by bus",
            "They must use a train, or travel separately, despite holding bus passes",
            "Many couples are forced to use other transport or separate buses, which is unfair",
            "The wife won't travel alone, so they can't use their bus passes together",
            "Buses sometimes have only one wheelchair space yet allow 3 pushchairs, walkers, "
            "luggage etc.",
            "This is an age of equal rights, so buses should have 2 wheelchair spaces",
        ),
    ),
    MultiClaimCase(
        petition_id="777880",
        text=(
            "Wildfires are becoming more frequent and more severe due to hotter, drier weather. "
            "Fire and Rescue Services often have to rely solely on ground crews, which can "
            "struggle to reach fires in remote areas such as moorland, forests and mountains. "
            "Wildfires are becoming more frequent and severe, putting lives, homes, wildlife and "
            "firefighters at greater risk. Many countries use dedicated firefighting aircraft to "
            "tackle large fires quickly, but we do not have a national fleet. The Government "
            "should fund and establish dedicated firefighting aircraft to support Fire and Rescue "
            "Services and improve our response to wildfires."
        ),
        demand=(
            "Strengthen wildfire response - funding for dedicated firefighting aircraft"
        ),
        conceded=None,
        claims=(
            "Wildfires are becoming more frequent and severe due to hotter, drier weather",
            "Fire and Rescue Services often rely solely on ground crews, who struggle to reach "
            "fires in remote areas like moorland, forests and mountains",
            "Wildfires put lives, homes, wildlife and firefighters at greater risk",
            "Many countries use dedicated firefighting aircraft to tackle large fires quickly, "
            "but this country has no national fleet",
            "The Government should fund and establish dedicated firefighting aircraft to support "
            "Fire and Rescue Services and improve wildfire response",
        ),
    ),
)

#: The items whose words concede an opposing view — the mirror rule's cases.
CONCEDING_CASES = tuple(c for c in MULTI_CLAIM_CASES if c.conceded)

