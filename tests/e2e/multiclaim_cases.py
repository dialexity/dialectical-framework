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

COMPOSITION, stated because it is not a random sample
=====================================================
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
- In 2 of the 40 the author's `demand` also appears verbatim inside `text`.
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
    """One real argument, its author's demand, and its conceded opposition."""

    petition_id: str
    text: str
    demand: str
    conceded: Optional[str]

    @property
    def url(self) -> str:
        return f"https://petition.parliament.uk/petitions/{self.petition_id}"


#: The 40 committed cases. `text` is what a writer under test sees; nothing else.
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
    ),
)

#: The items whose words concede an opposing view — the mirror rule's cases.
CONCEDING_CASES = tuple(c for c in MULTI_CLAIM_CASES if c.conceded)

